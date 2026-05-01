#!/usr/bin/env bash
# Désactive temporairement motor_service pour permettre le bringup d'un
# Pico W cimier (qui partage /dev/ttyACM0 avec le RP2040 moteur).
#
# Usage :
#   sudo bash scripts/diagnostics/pico_bringup_prepare.sh prepare
#   sudo bash scripts/diagnostics/pico_bringup_prepare.sh restore

set -euo pipefail

OVERRIDE_DIR="/etc/systemd/system/motor_service.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"

action="${1:-}"

if [[ "$EUID" -ne 0 ]]; then
    echo "Ce script doit etre lance en root."
    echo "Relance avec : sudo bash $0 $action"
    exit 1
fi

case "$action" in
    prepare)
        echo "[1/5] Creation du dossier override : $OVERRIDE_DIR"
        mkdir -p "$OVERRIDE_DIR"

        echo "[2/5] Ecriture du drop-in (Restart=no) dans $OVERRIDE_FILE"
        cat > "$OVERRIDE_FILE" <<'EOF'
[Service]
Restart=no
EOF

        echo "[3/5] systemctl daemon-reload"
        systemctl daemon-reload

        echo "[4/5] Stop + disable motor_service"
        systemctl stop motor_service || true
        systemctl disable motor_service || true

        echo "[5/5] Verification"
        sleep 1
        if systemctl is-active motor_service --quiet; then
            echo ""
            echo "ECHEC : motor_service est encore actif."
            systemctl status motor_service --no-pager | head -10
            exit 2
        fi
        echo ""
        echo "OK -- motor_service est arrete et ne redemarrera pas."
        echo "Tu peux maintenant lancer : uv run mpremote ls"
        echo ""
        echo "Quand le bringup sera termine, relance :"
        echo "  sudo bash $0 restore"
        ;;

    restore)
        echo "[1/4] Suppression du drop-in"
        rm -f "$OVERRIDE_FILE"
        rmdir "$OVERRIDE_DIR" 2>/dev/null || true

        echo "[2/4] systemctl daemon-reload"
        systemctl daemon-reload

        echo "[3/4] Re-enable + start motor_service"
        systemctl enable motor_service
        systemctl start motor_service

        echo "[4/4] Verification"
        sleep 2
        if systemctl is-active motor_service --quiet; then
            echo ""
            echo "OK -- motor_service est de nouveau actif."
        else
            echo ""
            echo "ATTENTION : motor_service ne tourne pas. Verifier :"
            systemctl status motor_service --no-pager | head -15
            exit 2
        fi
        ;;

    *)
        echo "Usage : sudo bash $0 prepare|restore"
        echo ""
        echo "  prepare   Stop motor_service + drop-in Restart=no (avant bringup Pico)"
        echo "  restore   Supprime le drop-in + re-enable motor_service (apres bringup)"
        exit 1
        ;;
esac
