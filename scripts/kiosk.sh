#!/bin/bash
# =============================================================================
# kiosk.sh - Ouvre le dashboard en plein écran (Firefox kiosque) au démarrage
# =============================================================================
# Lancé à l'ouverture de la session de bureau ; branché une fois pour toutes par
# scripts/install_kiosk.sh.
#
# Les services DriftApp attendent jusqu'à 90 s que le Pi soit remis à l'heure
# par internet (setup/time-wait-sync-timeout.conf) avant de démarrer Django.
# On attend donc que Django réponde, 5 min au plus, puis on ouvre Firefox de
# toute façon (sans Django, il affiche son erreur et « Try Again » suffit).
# =============================================================================

URL="http://localhost:8000"   # port fixé par driftapp_web.service

# Un seul kiosque, même si deux lanceurs subsistent au démarrage.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/driftapp-kiosk.lock"
flock -n 9 || exit 0

for _ in $(seq 1 150); do
    curl -s -o /dev/null --max-time 2 "$URL" && break
    sleep 2
done

NAVIGATEUR="$(command -v firefox || command -v firefox-esr)"
exec "$NAVIGATEUR" --kiosk "$URL"
