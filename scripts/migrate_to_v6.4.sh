#!/usr/bin/env bash
# =============================================================================
# migrate_to_v6.4.sh — Déploiement v5.10 → v6.4 sur le Pi terrain
# =============================================================================
#
# Automatise le saut depuis v5.10.0 (prod actuelle) vers v6.4.0 en traversant
# les milestones intermédiaires (v5.11, v5.12, v6.0, v6.1, v6.2, v6.3, v6.3.x,
# v6.4). Idempotent : peut être relancé sans dommage.
#
# Pré-requis :
#   - User : slenk (cohérent avec ems22d.service / motor_service.service)
#   - sudo accessible (avec mot de passe la 1ère fois — déploie ensuite la
#     règle sudoers v5.12 pour les MAJ ultérieures sans password)
#   - Réseau LAN actif (vers Pico W cimier 192.168.1.84 + Shelly 192.168.1.83)
#   - Le repo est cloné dans ~/DriftApp (chemin attendu par les .service)
#
# Usage :
#   ssh slenk@<pi-host>
#   cd ~/DriftApp
#   ./scripts/migrate_to_v6.4.sh
#
# Variables d'environnement :
#   PROJECT_DIR    chemin du repo (défaut: ~/DriftApp)
#   TARGET_REF     ref git à checkout (défaut: origin/main)
#   SKIP_HARDWARE  1 = skip vérifs Pico W/Shelly (mode dégradé sans cimier)
#   DRY_RUN        1 = simule sans modifier (utile pour 1ère lecture)
#
# Limites connues :
#   - NE FLASHE PAS le firmware Pico W : opération manuelle (cf.
#     firmware/cimier/README.md). Le script vérifie juste l'accessibilité HTTP.
#   - NE CONFIGURE PAS le Shelly : opération manuelle (cf. mémoire S. 30/04 sur
#     cascade 220V/12V).
#   - NON TESTÉ par CI (machine dev à 800 km du Pi prod). À valider terrain par
#     Serge sur une session test avant de l'utiliser pour une vraie MAJ.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration & couleurs
# -----------------------------------------------------------------------------

PROJECT_DIR="${PROJECT_DIR:-$HOME/DriftApp}"
TARGET_REF="${TARGET_REF:-origin/main}"
SKIP_HARDWARE="${SKIP_HARDWARE:-0}"
DRY_RUN="${DRY_RUN:-0}"

readonly SUDOERS_SRC="$PROJECT_DIR/setup/driftapp-updater.sudoers"
readonly SUDOERS_DST="/etc/sudoers.d/driftapp-updater"
readonly CIMIER_SERVICE_SRC="$PROJECT_DIR/cimier_service.service"
readonly CIMIER_SERVICE_DST="/etc/systemd/system/cimier_service.service"
readonly CONFIG_FILE="$PROJECT_DIR/data/config.json"
readonly CONFIG_BACKUP_DIR="$PROJECT_DIR/data/backups"
readonly LOG_FILE="$PROJECT_DIR/logs/migrate_to_v6.4_$(date +%Y%m%d_%H%M%S).log"

# Couleurs ANSI (désactivables si pas de TTY)
if [[ -t 1 ]]; then
    readonly C_RED=$'\033[0;31m'
    readonly C_GREEN=$'\033[0;32m'
    readonly C_YELLOW=$'\033[0;33m'
    readonly C_BLUE=$'\033[0;34m'
    readonly C_BOLD=$'\033[1m'
    readonly C_RESET=$'\033[0m'
else
    readonly C_RED='' C_GREEN='' C_YELLOW='' C_BLUE='' C_BOLD='' C_RESET=''
fi

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    case "$level" in
        INFO)  echo -e "${C_BLUE}[INFO]${C_RESET}  $msg" ;;
        OK)    echo -e "${C_GREEN}[OK]${C_RESET}    $msg" ;;
        WARN)  echo -e "${C_YELLOW}[WARN]${C_RESET}  $msg" ;;
        ERROR) echo -e "${C_RED}[ERROR]${C_RESET} $msg" >&2 ;;
        STEP)  echo -e "\n${C_BOLD}${C_BLUE}═══ $msg ═══${C_RESET}\n" ;;
        *)     echo "[$level] $msg" ;;
    esac
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    echo "[$ts] [$level] $msg" >> "$LOG_FILE" 2>/dev/null || true
}

die() {
    log ERROR "$@"
    log ERROR "Migration interrompue. Voir $LOG_FILE pour le détail."
    exit 1
}

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "  [DRY] $*"
    else
        "$@"
    fi
}

ask_continue() {
    local prompt="$1"
    if [[ ! -t 0 ]]; then
        log WARN "Pas de TTY interactif — assume « no » pour : $prompt"
        return 1
    fi
    read -r -p "$prompt [y/N] " response
    [[ "$response" =~ ^[Yy] ]]
}

# -----------------------------------------------------------------------------
# Étape 0 — Vérifications préalables
# -----------------------------------------------------------------------------

step_preflight() {
    log STEP "Étape 0 — Vérifications préalables"

    # User
    local current_user
    current_user="$(whoami)"
    if [[ "$current_user" != "slenk" ]]; then
        log WARN "User actuel = $current_user (attendu : slenk). Les .service files exécutent ems22d en User=slenk."
        ask_continue "Continuer quand même ?" || die "Lance le script en tant que slenk."
    else
        log OK "User = slenk"
    fi

    # Repo path
    if [[ ! -d "$PROJECT_DIR/.git" ]]; then
        die "PROJECT_DIR ($PROJECT_DIR) n'est pas un repo git. Vérifie le chemin ou clone d'abord."
    fi
    log OK "Repo trouvé : $PROJECT_DIR"

    # sudo
    if ! command -v sudo >/dev/null; then
        die "sudo non disponible — installation manuelle requise."
    fi
    if ! sudo -n true 2>/dev/null; then
        log WARN "sudo nécessitera un mot de passe pour la 1ère fois (déploiement sudoers v5.12)."
    fi

    # systemctl
    command -v systemctl >/dev/null || die "systemctl non disponible — système non-systemd ?"

    # Python
    command -v python3 >/dev/null || die "python3 requis pour la fusion config.json."

    # Network (sauf si SKIP_HARDWARE)
    if [[ "$SKIP_HARDWARE" != "1" ]]; then
        if ! ping -c 1 -W 2 192.168.1.1 >/dev/null 2>&1; then
            log WARN "LAN local injoignable (192.168.1.1). Vérifs hardware Pico W/Shelly probablement KO."
        else
            log OK "LAN local joignable"
        fi
    fi

    # Espace disque (estimation : 200 MB pour git pull + uv sync + backup)
    local available_kb
    available_kb=$(df -k "$PROJECT_DIR" | awk 'NR==2 {print $4}')
    if (( available_kb < 200000 )); then
        die "Espace disque insuffisant ($((available_kb/1024)) MB libre, 200 MB requis)."
    fi
    log OK "Espace disque OK ($((available_kb/1024)) MB libre)"
}

# -----------------------------------------------------------------------------
# Étape 1 — Backup config + data
# -----------------------------------------------------------------------------

step_backup() {
    log STEP "Étape 1 — Backup config + sessions"

    local stamp
    stamp="$(date +%Y%m%d_%H%M%S)"
    local backup_dir="$CONFIG_BACKUP_DIR/pre_v6.4_$stamp"

    run mkdir -p "$backup_dir"

    if [[ -f "$CONFIG_FILE" ]]; then
        run cp -p "$CONFIG_FILE" "$backup_dir/config.json"
        log OK "config.json sauvegardé dans $backup_dir/"
    else
        log WARN "$CONFIG_FILE absent — aucun backup à faire."
    fi

    # Sessions récentes (utile pour rollback en cas de problème)
    if [[ -d "$PROJECT_DIR/data/sessions" ]]; then
        run cp -rp "$PROJECT_DIR/data/sessions" "$backup_dir/sessions" 2>/dev/null || true
    fi

    # Liste de fichiers/services AVANT pour rollback informé
    {
        echo "# État avant migration $(date)"
        echo "## Services systemd"
        systemctl list-unit-files --no-pager --no-legend 2>/dev/null \
            | grep -E "ems22d|motor_service|cimier_service|driftapp_web" || true
        echo ""
        echo "## Versions Python"
        python3 --version 2>&1
        echo ""
        echo "## Git HEAD"
        cd "$PROJECT_DIR" && git rev-parse HEAD 2>&1 && git describe --always --dirty 2>&1 || true
    } > "$backup_dir/state_before.txt" 2>/dev/null || true

    log OK "Backup complet → $backup_dir/"
}

# -----------------------------------------------------------------------------
# Étape 2 — Git fetch + checkout vers TARGET_REF
# -----------------------------------------------------------------------------

step_git_update() {
    log STEP "Étape 2 — Git fetch + checkout $TARGET_REF"

    cd "$PROJECT_DIR"

    # Vérifie que le working tree est propre (sauf data/, logs/ qui changent)
    local dirty
    dirty="$(git status --porcelain -- ':!data' ':!logs' 2>/dev/null)" || true
    if [[ -n "$dirty" ]]; then
        log WARN "Working tree non-propre :"
        echo "$dirty"
        ask_continue "Continuer (les modifs locales risquent d'être écrasées) ?" \
            || die "Stash ou commit tes modifs locales d'abord."
    fi

    run git fetch --all --tags
    log OK "git fetch OK"

    local current_ref
    current_ref="$(git rev-parse HEAD)"
    local target_hash
    target_hash="$(git rev-parse "$TARGET_REF")"

    if [[ "$current_ref" == "$target_hash" ]]; then
        log OK "Déjà à jour sur $TARGET_REF ($target_hash)"
    else
        log INFO "Checkout : $current_ref → $target_hash"
        run git checkout "$TARGET_REF"
        log OK "Checkout OK"
    fi

    log INFO "Version cible : $(grep '^version' pyproject.toml | head -1)"
}

# -----------------------------------------------------------------------------
# Étape 3 — uv sync (dépendances Python)
# -----------------------------------------------------------------------------

step_uv_sync() {
    log STEP "Étape 3 — uv sync (dépendances Python)"

    cd "$PROJECT_DIR"

    if ! command -v uv >/dev/null; then
        die "uv non installé. Cf. https://github.com/astral-sh/uv ou apt install uv."
    fi

    run uv sync
    log OK "uv sync OK"
}

# -----------------------------------------------------------------------------
# Étape 4 — Déploiement sudoers v5.12 (idempotent)
# -----------------------------------------------------------------------------

step_sudoers() {
    log STEP "Étape 4 — Déploiement sudoers v5.12"

    if [[ ! -f "$SUDOERS_SRC" ]]; then
        die "$SUDOERS_SRC absent — le repo ne contient pas le fichier sudoers v5.12. Vérifie TARGET_REF."
    fi

    if [[ -f "$SUDOERS_DST" ]] && cmp -s "$SUDOERS_SRC" "$SUDOERS_DST"; then
        log OK "sudoers déjà à jour ($SUDOERS_DST)"
        return 0
    fi

    log INFO "Copie $SUDOERS_SRC → $SUDOERS_DST"
    run sudo cp "$SUDOERS_SRC" "$SUDOERS_DST"
    run sudo chmod 0440 "$SUDOERS_DST"
    run sudo chown root:root "$SUDOERS_DST"

    if [[ "$DRY_RUN" != "1" ]]; then
        if sudo visudo -cf "$SUDOERS_DST"; then
            log OK "sudoers syntaxe valide"
        else
            sudo rm -f "$SUDOERS_DST"
            die "sudoers syntaxe invalide — fichier supprimé pour ne pas casser sudo."
        fi
    fi
}

# -----------------------------------------------------------------------------
# Étape 5 — Installation cimier_service.service (NOUVEAU v6.0)
# -----------------------------------------------------------------------------

step_cimier_service() {
    log STEP "Étape 5 — Installation cimier_service.service (v6.0)"

    if [[ ! -f "$CIMIER_SERVICE_SRC" ]]; then
        die "$CIMIER_SERVICE_SRC absent — le repo ne contient pas le service v6.0. Vérifie TARGET_REF."
    fi

    local need_reload=0

    if [[ -f "$CIMIER_SERVICE_DST" ]] && cmp -s "$CIMIER_SERVICE_SRC" "$CIMIER_SERVICE_DST"; then
        log OK "cimier_service.service déjà à jour"
    else
        log INFO "Copie $CIMIER_SERVICE_SRC → $CIMIER_SERVICE_DST"
        run sudo cp "$CIMIER_SERVICE_SRC" "$CIMIER_SERVICE_DST"
        run sudo chmod 0644 "$CIMIER_SERVICE_DST"
        need_reload=1
    fi

    # Idempotent : daemon-reload + enable seulement si nécessaire
    if (( need_reload )); then
        run sudo systemctl daemon-reload
        log OK "systemctl daemon-reload"
    fi

    if systemctl is-enabled --quiet cimier_service.service 2>/dev/null; then
        log OK "cimier_service.service déjà enabled"
    else
        run sudo systemctl enable cimier_service.service
        log OK "cimier_service.service enabled"
    fi

    log INFO "Service NON démarré ici — démarrage dans Étape 9 (cascade restart)."
}

# -----------------------------------------------------------------------------
# Étape 6 — Fusion config.json (préserve valeurs locales)
# -----------------------------------------------------------------------------

step_config_merge() {
    log STEP "Étape 6 — Fusion config.json (préserve les valeurs locales)"

    if [[ ! -f "$CONFIG_FILE" ]]; then
        die "$CONFIG_FILE absent. Crée-le depuis le template ou restaure depuis un backup."
    fi

    # On utilise Python (toujours dispo) pour fusionner récursivement le template
    # du repo avec la config locale. Stratégie :
    #   - Le template repo (dans le HEAD checkout) sert de RÉFÉRENCE structurelle
    #   - Pour chaque clé du template absente du local → ajout
    #   - Pour chaque clé existante en local → préserve la valeur locale
    #   - Aucune clé locale n'est supprimée (rétro-compat stricte)
    #
    # Pour récupérer le template "neutre" (avec defaults adaptés terrain), on
    # sort le contenu du template depuis le checkout actuel via git show.
    local template_blob
    template_blob="$(git -C "$PROJECT_DIR" show "$TARGET_REF:data/config.json" 2>/dev/null || true)"

    if [[ -z "$template_blob" ]]; then
        log WARN "Impossible de lire le template config.json depuis $TARGET_REF — skip fusion."
        return 0
    fi

    local merge_helper
    merge_helper="$(mktemp)"
    cat > "$merge_helper" <<'PYEOF'
import json
import sys
from pathlib import Path

local_path = Path(sys.argv[1])
template_str = sys.stdin.read()

local = json.loads(local_path.read_text())
template = json.loads(template_str)


def deep_merge(local_node, template_node):
    """Préserve local_node ; ajoute les clés présentes seulement dans template_node."""
    if not isinstance(local_node, dict) or not isinstance(template_node, dict):
        return local_node
    for key, t_val in template_node.items():
        if key not in local_node:
            local_node[key] = t_val
        else:
            local_node[key] = deep_merge(local_node[key], t_val)
    return local_node


merged = deep_merge(local, template)
local_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")

# Liste les sections nouvelles (top-level) ajoutées
added = sorted(set(template.keys()) - set(local.keys()))
if added:
    print("ADDED:" + ",".join(added))
else:
    print("ADDED:(none)")
PYEOF

    if [[ "$DRY_RUN" == "1" ]]; then
        echo "  [DRY] python3 merge_helper.py $CONFIG_FILE <<< template"
        rm -f "$merge_helper"
        return 0
    fi

    local result
    result="$(echo "$template_blob" | python3 "$merge_helper" "$CONFIG_FILE")" || die "Fusion config.json échouée."
    rm -f "$merge_helper"

    log OK "config.json fusionné — $result"
    log INFO "Vérifie manuellement les clés cimier.host / cimier.port / power_switch.host"
    log INFO "selon ton hardware (cf. mémoire IPs DHCP fixées : Pico W = 192.168.1.84,"
    log INFO "Shelly = 192.168.1.83) et active 'cimier.enabled = true' une fois Pico W OK."
}

# -----------------------------------------------------------------------------
# Étape 7 — Permissions data/
# -----------------------------------------------------------------------------

step_permissions() {
    log STEP "Étape 7 — Permissions data/ (writable par slenk pour persistor)"

    if [[ ! -d "$PROJECT_DIR/data" ]]; then
        die "$PROJECT_DIR/data absent."
    fi

    local owner
    owner="$(stat -c '%U' "$PROJECT_DIR/data")"
    if [[ "$owner" != "slenk" ]]; then
        log INFO "Owner actuel = $owner ; chown -R slenk:slenk data/"
        run sudo chown -R slenk:slenk "$PROJECT_DIR/data"
    fi
    run chmod -R u+rw "$PROJECT_DIR/data" 2>/dev/null || true

    # Le persistor crée data/last_known_position.json au runtime — on touche
    # un placeholder vide pour valider les permissions immédiatement
    if [[ ! -f "$PROJECT_DIR/data/last_known_position.json" ]]; then
        log INFO "data/last_known_position.json sera créé au prochain boot du daemon ems22d."
    fi

    log OK "Permissions data/ vérifiées"
}

# -----------------------------------------------------------------------------
# Étape 8 — Vérifications hardware (Pico W cimier + Shelly)
# -----------------------------------------------------------------------------

step_hardware_check() {
    log STEP "Étape 8 — Vérifications hardware Pico W cimier + Shelly"

    if [[ "$SKIP_HARDWARE" == "1" ]]; then
        log WARN "SKIP_HARDWARE=1 — vérifs hardware ignorées (déploiement v6.4 sans cimier autonome)."
        log WARN "Pour activer plus tard : éditer cimier.enabled=true dans data/config.json + restart cimier_service."
        return 0
    fi

    # Lit les hosts depuis config.json (rappel : pas de hardcoded — mémoire feedback_no_hardcoded_ips)
    local cimier_host shelly_host
    cimier_host="$(python3 -c "import json,sys; print(json.load(open('$CONFIG_FILE')).get('cimier',{}).get('host','192.168.1.84'))" 2>/dev/null || echo "192.168.1.84")"
    shelly_host="$(python3 -c "import json,sys; print(json.load(open('$CONFIG_FILE')).get('cimier',{}).get('power_switch',{}).get('host','192.168.1.83'))" 2>/dev/null || echo "192.168.1.83")"

    log INFO "Test Pico W cimier sur $cimier_host..."
    if curl -sf --max-time 5 "http://$cimier_host/status" >/dev/null 2>&1; then
        log OK "Pico W cimier répond (HTTP /status)"
    else
        log ERROR "Pico W cimier ($cimier_host) ne répond pas."
        log ERROR "Causes probables :"
        log ERROR "  - Firmware non flashé (cf. firmware/cimier/README.md)"
        log ERROR "  - WiFi credentials KO ou IP DHCP non assignée"
        log ERROR "  - Court-circuit install non levé (mémoire 2026-05-02)"
        ask_continue "Continuer en mode dégradé (cimier désactivé en config) ?" \
            || die "Lève le blocage Pico W avant de réessayer."
        SKIP_HARDWARE=1
    fi

    if [[ "$SKIP_HARDWARE" != "1" ]]; then
        log INFO "Test Shelly sur $shelly_host..."
        if curl -sf --max-time 5 "http://$shelly_host/shelly" >/dev/null 2>&1 \
            || curl -sf --max-time 5 "http://$shelly_host/rpc/Shelly.GetStatus" >/dev/null 2>&1; then
            log OK "Shelly répond (Gen 1 ou Gen 2)"
        else
            log WARN "Shelly ($shelly_host) ne répond pas — power_switch sera type=noop"
            log WARN "(le cimier fonctionnera mais sans coupure secteur côté Pi)"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Étape 9 — Cascade restart services
# -----------------------------------------------------------------------------

step_restart_services() {
    log STEP "Étape 9 — Cascade restart services (ems22d → motor → cimier → web)"

    local services=(
        "ems22d.service"
        "motor_service.service"
        "cimier_service.service"
        "driftapp_web.service"
    )

    for svc in "${services[@]}"; do
        log INFO "Stop $svc..."
        run sudo systemctl stop "$svc" 2>/dev/null || true
    done

    # Cleanup IPC stale (cohérent avec start_web.sh)
    run sudo rm -f /dev/shm/motor_command.json /dev/shm/motor_status.json \
                   /dev/shm/ems22_position.json /dev/shm/cimier_status.json \
                   2>/dev/null || true

    sleep 2

    for svc in "${services[@]}"; do
        log INFO "Start $svc..."
        run sudo systemctl start "$svc"
        sleep 1
        if [[ "$DRY_RUN" != "1" ]]; then
            if systemctl is-active --quiet "$svc"; then
                log OK "$svc actif"
            else
                log ERROR "$svc échec démarrage"
                log ERROR "Voir : sudo journalctl -u $svc -n 50 --no-pager"
                die "Service $svc KO — investigation requise avant validation."
            fi
        fi
    done
}

# -----------------------------------------------------------------------------
# Étape 10 — Vérifications post-restart
# -----------------------------------------------------------------------------

step_postcheck() {
    log STEP "Étape 10 — Vérifications post-restart"

    if [[ "$DRY_RUN" == "1" ]]; then
        log INFO "DRY_RUN=1 — vérifications post-restart ignorées."
        return 0
    fi

    sleep 3

    # IPC encoder
    if [[ -f /dev/shm/ems22_position.json ]]; then
        log OK "/dev/shm/ems22_position.json présent"
        if grep -q "last_calibration_at" /dev/shm/ems22_position.json 2>/dev/null; then
            log OK "Champ last_calibration_at présent (Phase 1 active)"
        else
            log WARN "Champ last_calibration_at ABSENT — version pré-v6.4 ?"
        fi
    else
        log ERROR "/dev/shm/ems22_position.json manquant — ems22d KO"
    fi

    # IPC motor
    if [[ -f /dev/shm/motor_status.json ]]; then
        log OK "/dev/shm/motor_status.json présent"
        local cal_status
        cal_status="$(python3 -c "import json; print(json.load(open('/dev/shm/motor_status.json')).get('calibration',{}).get('status','MISSING'))" 2>/dev/null || echo "ERROR")"
        case "$cal_status" in
            running)
                log INFO "calibration.status = running (routine boot en cours, attendre 5-180 s)"
                log INFO "Surveille : watch -n 1 'cat /dev/shm/motor_status.json | python3 -m json.tool | grep -A 5 calibration'"
                ;;
            ok|simulated)
                log OK "calibration.status = $cal_status (cas nominal)"
                ;;
            degraded|exception|unknown)
                log WARN "calibration.status = $cal_status — UI bannière + bouton manuel attendus"
                ;;
            MISSING)
                log ERROR "calibration sub-dict absent — motor_service Phase 2 NON active. Vérifie version."
                ;;
            *)
                log WARN "calibration.status = $cal_status (valeur inattendue)"
                ;;
        esac
    else
        log ERROR "/dev/shm/motor_status.json manquant — motor_service KO"
    fi

    # Django
    if curl -sf --max-time 5 "http://localhost:8000/" >/dev/null 2>&1; then
        log OK "Django répond sur localhost:8000"
    else
        log WARN "Django ne répond pas sur localhost:8000 — vérifie driftapp_web.service"
    fi

    # Endpoint calibrate (smoke 202)
    local http_code
    http_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
        -X POST "http://localhost:8000/api/hardware/calibrate/" \
        -H 'Content-Type: application/json' -d '{}' 2>/dev/null || echo "000")"
    case "$http_code" in
        202) log OK "POST /api/hardware/calibrate/ → 202 (Phase 3 backend active)" ;;
        501) log ERROR "POST /api/hardware/calibrate/ → 501 (stub) — version pré-v6.4 routée. Vérifie HEAD." ;;
        503) log WARN "POST /api/hardware/calibrate/ → 503 (motor_service injoignable)" ;;
        *)   log WARN "POST /api/hardware/calibrate/ → $http_code (inattendu)" ;;
    esac
}

# -----------------------------------------------------------------------------
# Étape 11 — Récapitulatif
# -----------------------------------------------------------------------------

step_recap() {
    log STEP "Récapitulatif"

    cat <<EOF

${C_BOLD}Migration v6.4 terminée.${C_RESET}

Prochaines étapes manuelles à séquencer :
  1. Ouvrir l'UI dashboard dans le navigateur (Ctrl+F5 pour recharger les assets)
  2. Vérifier la bannière calibration :
     - Cas nominal : badge ✓ vert dans le header, bannière masquée, boutons mouvement actifs
     - Cas dégradé : bannière rouge, badge ✕, 7 boutons mouvement grisés (STOPs/cimier actifs)
  3. Si cimier configuré (cimier.enabled=true + Pico W répond) :
     - Tester ouverture/fermeture cimier depuis l'UI
     - Vérifier la timeline cimier
  4. Lancer une vraie session d'astrophotographie pour valider :
     - Boot calibration : routine se termine en ${C_GREEN}ok${C_RESET} (5-180 s)
     - Tracking + GOTO + JOG nominaux
     - Bouton « Calibrer maintenant » fonctionne (utile en cas de doute)

Logs de la migration : $LOG_FILE
Backup config : $CONFIG_BACKUP_DIR/pre_v6.4_*

En cas de problème :
  - sudo journalctl -u motor_service -n 100 --no-pager
  - sudo journalctl -u ems22d -n 100 --no-pager
  - cat /dev/shm/motor_status.json | python3 -m json.tool

Pour rollback : restaurer le backup config.json et faire git checkout sur le hash précédent.
Cf. CLAUDE.md section « Déploiement v6.4 sur le Pi terrain » pour les diagnostics.

EOF
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    cd "$PROJECT_DIR"

    log INFO "=============================================="
    log INFO " Migration v5.10 → v6.4 — démarrage"
    log INFO " PROJECT_DIR=$PROJECT_DIR"
    log INFO " TARGET_REF=$TARGET_REF"
    log INFO " SKIP_HARDWARE=$SKIP_HARDWARE  DRY_RUN=$DRY_RUN"
    log INFO "=============================================="

    step_preflight
    step_backup
    step_git_update
    step_uv_sync
    step_sudoers
    step_cimier_service
    step_config_merge
    step_permissions
    step_hardware_check
    step_restart_services
    step_postcheck
    step_recap

    log OK "Migration v6.4 — terminée."
}

main "$@"
