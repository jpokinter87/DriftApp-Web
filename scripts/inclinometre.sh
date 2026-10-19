#!/usr/bin/env bash
# Raccourcis pour l'inclinomètre de la monture, à taper au clavier sur le Pi.
# Protocole : docs/protocole_inclinometre_terrain.pdf
#
#   ./scripts/inclinometre.sh scan       lister les appareils Bluetooth visibles
#   ./scripts/inclinometre.sh essai      acquisition dans le terminal (Ctrl+C pour arrêter)
#   ./scripts/inclinometre.sh demarrer   acquisition en tâche de fond (survit à la fermeture du terminal)
#   ./scripts/inclinometre.sh etat       acquisition en cours ? + dernières lignes
#   ./scripts/inclinometre.sh arreter    arrêter l'acquisition en tâche de fond
#
# essai et demarrer acceptent --adresse AA:BB:CC:DD:EE:FF si plusieurs capteurs sont visibles.

set -u
cd "$(dirname "$0")/.." || exit 1

LANCER=(uv run --with bleak python scripts/diagnostics/inclinometre_monture.py)
CONSOLE=logs/diagnostics/inclinometre_console.txt
MOTIF=inclinometre_monture.py

en_cours() { pgrep -f "$MOTIF" >/dev/null; }

case "${1:-}" in
    scan)
        "${LANCER[@]}" --scan
        ;;
    essai)
        "${LANCER[@]}" "${@:2}"
        ;;
    demarrer)
        if en_cours; then
            echo "L'acquisition tourne déjà."
            exit 0
        fi
        mkdir -p logs/diagnostics
        nohup "${LANCER[@]}" "${@:2}" >"$CONSOLE" 2>&1 &
        sleep 2
        echo "Acquisition lancée en tâche de fond. Vérifier avec : ./scripts/inclinometre.sh etat"
        ;;
    etat)
        if en_cours; then echo "Acquisition EN COURS"; else echo "Acquisition ARRÊTÉE"; fi
        if [ -f "$CONSOLE" ]; then
            echo "--- dernières lignes de $CONSOLE ---"
            tail -n 5 "$CONSOLE"
        fi
        ;;
    arreter)
        if en_cours; then
            pkill -f "$MOTIF"
            echo "Acquisition arrêtée."
        else
            echo "Aucune acquisition en cours."
        fi
        ;;
    *)
        echo "Usage : ./scripts/inclinometre.sh scan | essai | demarrer | etat | arreter"
        exit 1
        ;;
esac
