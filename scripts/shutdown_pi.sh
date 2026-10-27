#!/bin/bash
# =============================================================================
# shutdown_pi.sh - Extinction propre du Raspberry Pi depuis le dashboard
# =============================================================================
# Lancé par Django via `sudo` (NOPASSWD whitelist : setup/driftapp-updater.sudoers),
# après vérification que la session est rangée (suivi arrêté, cimier fermé).
#
# Raison d'être : couper le courant sans arrêt propre laisse des logs tronqués
# et fait repartir le Pi à une heure fausse (nuit du 26/10/2026).
#
# L'extinction part 3 s plus tard, en arrière-plan : la réponse HTTP du bouton
# doit avoir quitté Django avant que systemd l'arrête.
#
# Usage :
#   sudo ./scripts/shutdown_pi.sh
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/shutdown.log"
# sudo efface l'environnement : la variable ne sert qu'aux tests.
MODEL_FILE="${DRIFTAPP_MODEL_FILE:-/proc/device-tree/model}"

mkdir -p "$LOG_DIR"
REPO_OWNER="$(stat -c '%U' "$PROJECT_DIR" 2>/dev/null || echo root)"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
    chown "$REPO_OWNER:$REPO_OWNER" "$LOG_FILE" 2>/dev/null || true
}

# Garde : un essai en dev ne doit jamais éteindre le PC de développement.
if ! tr -d '\0' < "$MODEL_FILE" 2>/dev/null | grep -q "Raspberry Pi"; then
    log "Extinction refusée : ce n'est pas un Raspberry Pi"
    echo "SHUTDOWN_REFUSED not a Raspberry Pi"
    exit 1
fi

log "=== Extinction du Pi demandée depuis le dashboard ==="
setsid nohup bash -c "sleep 3; systemctl poweroff" > /dev/null 2>&1 < /dev/null &
echo "SHUTDOWN_SCHEDULED"
