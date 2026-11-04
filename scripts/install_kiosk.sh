#!/bin/bash
# =============================================================================
# install_kiosk.sh - Branche scripts/kiosk.sh sur le démarrage du bureau du Pi
# =============================================================================
# À taper une fois sur le Pi, dans un terminal du bureau (pas en sudo) :
#   cd ~/DriftApp && ./scripts/install_kiosk.sh
#
# Le lancement de Firefox au démarrage a été réglé à la main en juin, hors du
# dépôt. Ce script le retrouve dans les fichiers de démarrage du bureau et y
# remplace la commande du navigateur par kiosk.sh, en gardant le même
# mécanisme (celui qui marche sur ce Pi). Copie de chaque fichier modifié en
# <fichier>.avant-kiosk. S'il ne trouve rien, il crée une entrée d'autostart.
# Le relancer ne change rien.
# =============================================================================

set -euo pipefail

KIOSK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/kiosk.sh"
CFG="$HOME/.config"
NAV='firefox|chromium'   # commandes du navigateur à remplacer

if [ "$(id -u)" -eq 0 ]; then
    echo "À lancer sans sudo (le démarrage du bureau est celui de l'utilisateur)."
    exit 1
fi
chmod +x "$KIOSK"

# Lignes non commentées qui lancent un navigateur.
lance_navigateur() { grep -qiE "^[^#]*($NAV)" "$1" 2>/dev/null; }

FICHIERS=("$CFG"/autostart/*.desktop "$CFG/labwc/autostart" "$CFG/wayfire.ini"
          "$CFG/lxsession/LXDE-pi/autostart")

if grep -qsF "$KIOSK" "${FICHIERS[@]}"; then
    echo "Kiosque déjà installé, rien à faire."
    exit 0
fi

modifies=0
for f in "${FICHIERS[@]}"; do
    [ -f "$f" ] && lance_navigateur "$f" || continue
    case "$f" in
        *.desktop)        motif="s%^Exec=.*($NAV).*%Exec=$KIOSK%I" ;;
        */labwc/autostart) motif="s%^[^#]*($NAV).*%\"$KIOSK\" \&%I" ;;
        */wayfire.ini)    motif="s%^([^#=]*=[[:space:]]*).*($NAV).*%\1$KIOSK%I" ;;
        *)                motif="s%^@?[^#]*($NAV).*%@$KIOSK%I" ;;
    esac
    sed -i.avant-kiosk -E "$motif" "$f"
    echo "Modifié : $f (copie de l'ancien en $f.avant-kiosk)"
    modifies=$((modifies + 1))
done

if [ "$modifies" -eq 0 ]; then
    mkdir -p "$CFG/autostart"
    cat > "$CFG/autostart/driftapp-kiosk.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=DriftApp kiosque
Exec=$KIOSK
DESKTOP
    echo "Aucun ancien lancement trouvé : créé $CFG/autostart/driftapp-kiosk.desktop"
fi
echo "Terminé. Redémarrer le Pi pour vérifier."
