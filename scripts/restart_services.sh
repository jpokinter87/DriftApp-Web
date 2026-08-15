#!/bin/bash
# =============================================================================
# restart_services.sh - Redémarrage des services backend DriftApp
# =============================================================================
# Lancé par Django via `sudo` (NOPASSWD whitelist : setup/driftapp-updater.sudoers).
#
# Raison d'être : une modification faite depuis la page /configuration/ n'a
# d'effet qu'après un redémarrage des services qui lisent data/config.json.
# Sans ce script, appliquer un changement de configuration imposait un accès
# SSH — impossible pour un observatoire piloté à distance.
#
# Redémarre l'encodeur, le moteur et le cimier. **Pas Django** : il porte la
# requête HTTP du bouton (la couper priverait l'utilisateur du résultat), et
# c'est inutile — la sauvegarde de configuration invalide déjà son cache.
#
# Écrit son résultat dans logs/restart_status.json, lu par la vue.
#
# Usage :
#   sudo ./scripts/restart_services.sh
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
STATUS_FILE="$LOG_DIR/restart_status.json"
LOG_FILE="$LOG_DIR/restart.log"

SERVICES=(ems22d.service motor_service.service cimier_service.service)

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Propriétaire du dépôt : les fichiers écrits en root doivent rester lisibles
# et réinscriptibles par l'utilisateur qui fait tourner Django.
REPO_OWNER="$(stat -c '%U' "$PROJECT_DIR" 2>/dev/null || echo root)"

write_status() {
    local done_flag="$1" message="$2" results="$3"
    cat > "$STATUS_FILE" <<EOF
{
  "done": $done_flag,
  "message": "$message",
  "services": $results,
  "timestamp": "$(date '+%Y-%m-%dT%H:%M:%S')"
}
EOF
    chown "$REPO_OWNER:$REPO_OWNER" "$STATUS_FILE" 2>/dev/null || true
}

log "=== Redémarrage des services demandé ==="
write_status false "Redémarrage en cours..." "[]"

results=""
failures=0
restarted=0

for svc in "${SERVICES[@]}"; do
    # Un service non installé sur ce Pi ne doit pas faire échouer les autres.
    if ! systemctl list-unit-files "$svc" 2>/dev/null | grep -q "$svc"; then
        log "$svc : non installé, ignoré"
        results="$results{\"name\":\"$svc\",\"state\":\"absent\"},"
        continue
    fi

    restarted=$((restarted + 1))

    log "Restart $svc"
    systemctl restart "$svc" 2>>"$LOG_FILE"
    sleep 2

    if systemctl is-active --quiet "$svc"; then
        log "$svc actif"
        results="$results{\"name\":\"$svc\",\"state\":\"active\"},"
    else
        log "ERREUR : $svc non actif après redémarrage"
        journalctl -u "$svc" -n 10 --no-pager 2>/dev/null >> "$LOG_FILE" || true
        results="$results{\"name\":\"$svc\",\"state\":\"failed\"},"
        failures=$((failures + 1))
    fi
done

results="[${results%,}]"

if [ "$failures" -eq 0 ]; then
    if [ "$restarted" -eq 0 ]; then
        # Annoncer un redémarrage qui n'a pas eu lieu masquerait une
        # installation incomplète : les unités systemd ne sont pas en place.
        write_status true "Aucun service installé sur cette machine" "$results"
        log "=== Terminé : aucune unité systemd trouvée ==="
        exit 0
    fi
    write_status true "Services redémarrés" "$results"
    log "=== Terminé : tous les services sont actifs ==="
    exit 0
fi

write_status true "$failures service(s) non redémarré(s)" "$results"
log "=== Terminé avec $failures échec(s) ==="
exit 1
