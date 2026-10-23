#!/usr/bin/env bash
# Surveillance de la monture via l'ASIAIR, à taper directement sur le Pi (depuis ~/DriftApp).
# Depuis la 6.25 elle tourne en permanence (service asiair_monitor) :
#   ./scripts/asiair_sonde.sh etat       service actif ou non + dernières lignes du journal
#   ./scripts/asiair_sonde.sh arreter    arrête une ancienne sonde lancée à la main avant la 6.25
set -u
cd "$(dirname "$0")/.." || exit 1

JOURNAL=logs/asiair/asiair_monitor.log
ANCIENNE=scripts/diagnostics/asiair_sonde.py

case "${1:-}" in
    etat)
        if systemctl is-active --quiet asiair_monitor.service; then
            echo "Surveillance EN COURS (service asiair_monitor)"
        else
            echo "Surveillance ARRÊTÉE (service asiair_monitor) — « Redémarrer les services » sur la page Configuration"
        fi
        if [ -f "$JOURNAL" ]; then
            echo "--- dernières lignes de $JOURNAL ---"
            tail -n 8 "$JOURNAL"
        fi
        ;;
    arreter)
        if pgrep -f "$ANCIENNE" >/dev/null; then
            pkill -f "$ANCIENNE"
            echo "Ancienne sonde arrêtée. La surveillance permanente continue."
        else
            echo "Aucune ancienne sonde en cours. La surveillance permanente n'est pas concernée."
        fi
        ;;
    *)
        echo "Usage : ./scripts/asiair_sonde.sh etat | arreter"
        echo "(depuis la 6.25 la surveillance tourne en permanence : plus rien à démarrer)"
        exit 1
        ;;
esac
