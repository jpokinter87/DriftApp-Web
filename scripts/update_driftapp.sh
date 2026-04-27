#!/bin/bash
# =============================================================================
# update_driftapp.sh - Mise à jour DriftApp Web (v5.12.0)
# =============================================================================
# Lancé par Django via `sudo` (NOPASSWD whitelist : setup/driftapp-updater.sudoers).
# S'auto-détache en background et écrit sa progression dans :
#   - logs/update_status.json : état machine-readable (phase, step/total, done)
#   - logs/update.log         : log texte détaillé pour debug
#
# Étapes (5 au total) :
#   1. stop_services : stop motor_service, ems22d
#   2. fetch         : stash + pull (préserve les modifs locales de l'utilisateur)
#   3. deps          : uv sync --extra dev
#   4. services      : install .service + daemon-reload
#   5. restart       : start ems22d, motor_service, driftapp_web
#
# Préservation config utilisateur (config_strategy, défaut "keep") :
#   - "keep"  : stash + pop avec priorité user (comportement v5.8.0)
#               Fichiers trackés modifiés → backup en <file>.user_backup.<ts>
#               Version upstream conflictuelle disponible en <file>.upstream
#   - "reset" : data/config.json est checkout sur origin/main AVANT le pull
#               (l'ancien local est sauvé en data/config.json.user_backup.<ts>)
#               Le reste du stash (autres fichiers user) est appliqué normalement.
#
# Usage :
#   sudo ./scripts/update_driftapp.sh                           # mode UI détaché, keep
#   sudo ./scripts/update_driftapp.sh --config-strategy reset   # idem, reset config
#   sudo ./scripts/update_driftapp.sh --detached                # mode background
#   sudo ./scripts/update_driftapp.sh --foreground              # mode manuel (debug)
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
STATUS_FILE="$LOG_DIR/update_status.json"
LOG_FILE="$LOG_DIR/update.log"
SERVICE_DIR="/etc/systemd/system"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
TOTAL=5

mkdir -p "$LOG_DIR"

# =============================================================================
# Parse args : --config-strategy {keep|reset}, --detached, --foreground
# =============================================================================
CONFIG_STRATEGY="keep"
RUN_MODE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --config-strategy)
            CONFIG_STRATEGY="${2:-keep}"
            shift 2
            ;;
        --detached|--foreground)
            RUN_MODE="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if [ "$CONFIG_STRATEGY" != "keep" ] && [ "$CONFIG_STRATEGY" != "reset" ]; then
    echo "ERREUR : --config-strategy doit être 'keep' ou 'reset' (reçu: $CONFIG_STRATEGY)" >&2
    exit 2
fi

# =============================================================================
# Détachement automatique (sauf --detached ou --foreground)
# =============================================================================
if [ "$RUN_MODE" != "--detached" ] && [ "$RUN_MODE" != "--foreground" ]; then
    # Réinitialiser le status + log pour cette session
    : > "$LOG_FILE"
    nohup "$0" --detached --config-strategy "$CONFIG_STRATEGY" >> "$LOG_FILE" 2>&1 &
    echo "UPDATE_STARTED pid=$!"
    exit 0
fi

# =============================================================================
# Helpers
# =============================================================================
now() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(now)] $*"; }

# Échappe une string pour JSON (backslash, quotes, newlines)
json_escape() {
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<< "$1"
}

write_status() {
    # write_status <phase> <step> <message> [success:null|true|false] [done:true|false] [error:""]
    local phase="$1" step="$2" message="$3"
    local success="${4:-null}" done_flag="${5:-false}" error_raw="${6:-}"
    local message_json error_json
    message_json="$(json_escape "$message")"
    if [ -n "$error_raw" ]; then
        error_json="$(json_escape "$error_raw")"
    else
        error_json="null"
    fi
    cat > "$STATUS_FILE" <<EOF
{
  "phase": "$phase",
  "step": $step,
  "total": $TOTAL,
  "message": $message_json,
  "success": $success,
  "done": $done_flag,
  "error": $error_json,
  "timestamp": "$(now)"
}
EOF
    # Permissions lisibles par Django
    chmod 0644 "$STATUS_FILE" 2>/dev/null || true
}

# Détermine l'utilisateur propriétaire du dépôt (pour git en non-root)
if [ -d "$PROJECT_DIR/.git" ]; then
    REPO_OWNER="$(stat -c '%U' "$PROJECT_DIR/.git" 2>/dev/null || echo 'slenk')"
else
    REPO_OWNER="${SUDO_USER:-slenk}"
fi
run_as_owner() { sudo -u "$REPO_OWNER" "$@"; }

# =============================================================================
# Démarrage
# =============================================================================
write_status "starting" 0 "Démarrage de la mise à jour..."
log "=== Mise à jour DriftApp Web ==="
log "Projet : $PROJECT_DIR | Owner dépôt : $REPO_OWNER | TS : $TIMESTAMP"

# =============================================================================
# ÉTAPE 1/5 : arrêt services moteur/encodeur
# =============================================================================
write_status "stop_services" 1 "Arrêt de motor_service et ems22d..."
log "--- Étape 1/5 : Arrêt services ---"

stop_service() {
    local svc="$1"
    log "Stop $svc"
    systemctl stop "$svc" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        systemctl is-active --quiet "$svc" 2>/dev/null || return 0
        sleep 1
    done
    log "Forçage kill $svc"
    systemctl kill "$svc" 2>/dev/null || true
    sleep 2
    systemctl is-active --quiet "$svc" && log "WARN : $svc toujours actif" || true
}

stop_service "motor_service.service"
stop_service "ems22d.service"
pkill -f "motor_service.py" 2>/dev/null || true
sleep 1

# =============================================================================
# ÉTAPE 2/5 : fetch (stash + pull avec préservation config user)
# =============================================================================
write_status "fetch" 2 "Téléchargement des mises à jour (git)..."
log "--- Étape 2/5 : stash + pull ---"

cd "$PROJECT_DIR" || { write_status "fetch" 2 "cd échoué" false true "cd $PROJECT_DIR"; exit 1; }
chown -R "$REPO_OWNER:$REPO_OWNER" "$PROJECT_DIR/.git" 2>/dev/null || true

OLD_COMMIT="$(run_as_owner git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
log "HEAD avant : $OLD_COMMIT | config_strategy : $CONFIG_STRATEGY"

# Stratégie reset : checkout upstream de data/config.json AVANT le stash, pour que
# le pull s'applique sans conflit sur ce fichier. L'ancien local est sauvegardé.
# Pré-fetch indispensable pour avoir une référence origin/main à jour.
if [ "$CONFIG_STRATEGY" = "reset" ]; then
    log "config_strategy=reset : pré-fetch + checkout origin/main de data/config.json"
    run_as_owner git fetch origin main >> "$LOG_FILE" 2>&1 || log "WARN : pré-fetch échoué"
    if [ -f "$PROJECT_DIR/data/config.json" ]; then
        cp -p "$PROJECT_DIR/data/config.json" \
            "$PROJECT_DIR/data/config.json.user_backup.$TIMESTAMP" 2>/dev/null \
            && log "Backup local : data/config.json.user_backup.$TIMESTAMP"
    fi
    if run_as_owner git checkout origin/main -- data/config.json >> "$LOG_FILE" 2>&1; then
        log "data/config.json remplacé par la version upstream"
    else
        log "WARN : checkout upstream de data/config.json échoué"
    fi
fi

# Liste des fichiers trackés modifiés (staged + unstaged)
MODIFIED_FILES="$(run_as_owner git status --porcelain 2>/dev/null \
    | awk '/^[ MADRCU?][MADRCU]|^[MADRCU][ MADRCU]/ {print $2}' \
    | sort -u)"

# Backup des fichiers modifiés par l'utilisateur
STASH_APPLIED=false
if [ -n "$MODIFIED_FILES" ]; then
    log "Fichiers modifiés localement :"
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        log "  - $f"
        if [ -f "$PROJECT_DIR/$f" ]; then
            cp -p "$PROJECT_DIR/$f" "$PROJECT_DIR/$f.user_backup.$TIMESTAMP" 2>/dev/null || true
        fi
    done <<< "$MODIFIED_FILES"

    log "Création du stash..."
    if run_as_owner git stash push --include-untracked=false \
        -m "driftapp-auto-$TIMESTAMP" >> "$LOG_FILE" 2>&1; then
        STASH_APPLIED=true
        log "Stash créé"
    else
        log "Stash échoué — on tente le pull avec les modifs en place"
    fi
fi

# Fetch puis pull
log "git fetch origin main..."
run_as_owner git fetch origin main >> "$LOG_FILE" 2>&1 || log "WARN : fetch échoué"

log "git pull --ff-only origin main..."
if run_as_owner git pull --ff-only origin main >> "$LOG_FILE" 2>&1; then
    NEW_COMMIT="$(run_as_owner git rev-parse --short HEAD)"
    log "Pull OK : $OLD_COMMIT → $NEW_COMMIT"
else
    log "ERREUR : pull échoué"
    # Restaurer stash si pull a raté
    if [ "$STASH_APPLIED" = true ]; then
        run_as_owner git stash pop >> "$LOG_FILE" 2>&1 || true
    fi
    write_status "fetch" 2 "Échec du git pull (voir update.log)" false true "git pull failed"
    exit 1
fi

# Pop stash avec stratégie de préservation utilisateur
if [ "$STASH_APPLIED" = true ]; then
    log "Restauration des modifs locales (priorité utilisateur en cas de conflit)..."
    if run_as_owner git stash pop >> "$LOG_FILE" 2>&1; then
        log "Stash restauré sans conflit"
    else
        log "Conflits détectés — résolution avec priorité utilisateur"
        CONFLICTS="$(run_as_owner git diff --name-only --diff-filter=U 2>/dev/null)"
        if [ -n "$CONFLICTS" ]; then
            while IFS= read -r f; do
                [ -z "$f" ] && continue
                log "Conflit : $f → version user gardée, upstream en $f.upstream"
                # Version upstream = celle qui vient d'être pull (stage 1 ou HEAD)
                run_as_owner git show ":1:$f" > "$PROJECT_DIR/$f.upstream" 2>/dev/null \
                    || run_as_owner git show HEAD:"$f" > "$PROJECT_DIR/$f.upstream" 2>/dev/null \
                    || log "WARN : impossible d'extraire la version upstream de $f"
                # Garder la version user (stash = stage 3 = theirs dans un stash pop)
                run_as_owner git checkout --theirs -- "$f" 2>/dev/null || true
                run_as_owner git reset HEAD -- "$f" 2>/dev/null || true
            done <<< "$CONFLICTS"
            run_as_owner git stash drop 2>/dev/null || true
        fi
    fi
fi

# =============================================================================
# ÉTAPE 3/5 : uv sync
# =============================================================================
write_status "deps" 3 "Synchronisation des dépendances Python (uv sync)..."
log "--- Étape 3/5 : uv sync ---"

if command -v uv &>/dev/null; then
    if run_as_owner uv sync --extra dev >> "$LOG_FILE" 2>&1; then
        log "Dépendances synchronisées"
    else
        log "WARN : uv sync a échoué — l'environnement peut être incohérent"
    fi
else
    log "uv non installé — étape sautée"
fi

# =============================================================================
# ÉTAPE 4/5 : install services systemd
# =============================================================================
write_status "services" 4 "Installation des fichiers de service systemd..."
log "--- Étape 4/5 : services systemd ---"

for svc in ems22d.service motor_service.service driftapp_web.service; do
    if [ -f "$PROJECT_DIR/$svc" ]; then
        if cmp -s "$PROJECT_DIR/$svc" "$SERVICE_DIR/$svc" 2>/dev/null; then
            log "$svc : inchangé"
        else
            cp "$PROJECT_DIR/$svc" "$SERVICE_DIR/" && log "$svc installé"
        fi
    else
        log "WARN : $PROJECT_DIR/$svc non trouvé"
    fi
done
systemctl daemon-reload
log "daemon-reload OK"

# v5.12.0 : redéploiement automatique du sudoers — évite que les MAJ futures
# qui ajoutent des args au script soient bloquées par un sudoers obsolète.
SUDOERS_SRC="$PROJECT_DIR/setup/driftapp-updater.sudoers"
SUDOERS_DST="/etc/sudoers.d/driftapp-updater"
if [ -f "$SUDOERS_SRC" ]; then
    if ! cmp -s "$SUDOERS_SRC" "$SUDOERS_DST" 2>/dev/null; then
        if cp "$SUDOERS_SRC" "$SUDOERS_DST" 2>/dev/null && chmod 0440 "$SUDOERS_DST" 2>/dev/null; then
            if visudo -cf "$SUDOERS_DST" >> "$LOG_FILE" 2>&1; then
                log "Sudoers mis à jour : $SUDOERS_DST"
            else
                log "WARN : visudo a rejeté le nouveau sudoers — restoration nécessaire"
            fi
        else
            log "WARN : impossible de copier le sudoers (besoin root ?)"
        fi
    else
        log "Sudoers : inchangé"
    fi
fi

# Réalignement des permissions (logs et data accessibles à l'user Django)
chown -R "$REPO_OWNER:$REPO_OWNER" "$LOG_DIR" 2>/dev/null || true
chown -R "$REPO_OWNER:$REPO_OWNER" "$PROJECT_DIR/data" 2>/dev/null || true

# =============================================================================
# ÉTAPE 5/5 : restart services
# =============================================================================
write_status "restart" 5 "Redémarrage des services..."
log "--- Étape 5/5 : restart ---"

start_service() {
    local svc="$1"
    systemctl enable "$svc" 2>/dev/null || true
    systemctl restart "$svc"
    sleep 2
    if systemctl is-active --quiet "$svc"; then
        log "$svc actif"
    else
        log "ERREUR : $svc non actif"
        journalctl -u "$svc" -n 10 --no-pager 2>/dev/null >> "$LOG_FILE" || true
    fi
}

start_service "ems22d.service"
start_service "motor_service.service"

# Marquer done AVANT de redémarrer Django (sinon le status n'est jamais écrit
# si Django crashe au restart)
write_status "done" 5 "Mise à jour terminée avec succès" true true
log "=== Mise à jour terminée — redémarrage Django ==="

start_service "driftapp_web.service"

exit 0
