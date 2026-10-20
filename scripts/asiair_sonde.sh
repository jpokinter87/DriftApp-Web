#!/usr/bin/env bash
# Surveillance de la monture via l'ASIAIR, à taper directement sur le Pi (depuis ~/DriftApp) :
#   ./scripts/asiair_sonde.sh essai      dans le terminal, Ctrl+C pour arrêter
#   ./scripts/asiair_sonde.sh demarrer   en tâche de fond pour la nuit (survit à la fermeture du terminal)
#   ./scripts/asiair_sonde.sh etat       en cours ou non + dernières lignes
#   ./scripts/asiair_sonde.sh arreter
set -u
cd "$(dirname "$0")/.." || exit 1

LANCER=(uv run python scripts/diagnostics/asiair_sonde.py)
CONSOLE=logs/diagnostics/asiair_console.txt
MOTIF=asiair_sonde.py

en_cours() { pgrep -f "$MOTIF" >/dev/null; }

case "${1:-}" in
    essai)
        "${LANCER[@]}" "${@:2}"
        ;;
    demarrer)
        if en_cours; then
            echo "La surveillance tourne déjà."
            exit 0
        fi
        mkdir -p logs/diagnostics
        nohup "${LANCER[@]}" "${@:2}" >"$CONSOLE" 2>&1 &
        sleep 3
        echo "Surveillance lancée en tâche de fond. Vérifier avec : ./scripts/asiair_sonde.sh etat"
        ;;
    etat)
        if en_cours; then echo "Surveillance EN COURS"; else echo "Surveillance ARRÊTÉE"; fi
        if [ -f "$CONSOLE" ]; then
            echo "--- dernières lignes de $CONSOLE ---"
            tail -n 8 "$CONSOLE"
        fi
        ;;
    arreter)
        if en_cours; then
            pkill -f "$MOTIF"
            echo "Surveillance arrêtée."
        else
            echo "Aucune surveillance en cours."
        fi
        ;;
    *)
        echo "Usage : ./scripts/asiair_sonde.sh essai | demarrer | etat | arreter"
        exit 1
        ;;
esac
