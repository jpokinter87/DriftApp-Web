#!/bin/bash
#
# Script de déploiement DriftApp v4.4
# 
# Usage:
#   chmod +x deploy_v4.4.sh
#   ./deploy_v4.4.sh
#
# Ce script:
# 1. Crée une sauvegarde des fichiers existants
# 2. Copie les nouveaux fichiers
# 3. Redémarre les services
#

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║              DÉPLOIEMENT DRIFTAPP v4.4                           ║"
echo "║              Correction des saccades GOTO                        ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Vérifier qu'on est dans le bon répertoire
if [ ! -f "start_web.sh" ]; then
    echo -e "${RED}❌ Erreur: Ce script doit être lancé depuis le répertoire DriftApp${NC}"
    echo "   Ex: cd ~/Dome_v4_6 && ./deploy_v4.4.sh"
    exit 1
fi

# Vérifier les fichiers sources
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"

if [ ! -f "$SOURCE_DIR/motor_service.py" ]; then
    echo -e "${RED}❌ Erreur: Fichiers sources non trouvés${NC}"
    echo "   Assurez-vous que motor_service.py, config.json et adaptive_tracking.py"
    echo "   sont dans le même répertoire que ce script."
    exit 1
fi

echo -e "${GREEN}✓ Fichiers sources trouvés${NC}"
echo ""

# Créer le répertoire de backup
BACKUP_DIR="backups/v4.3_$(date +%Y%m%d_%H%M%S)"
echo "📁 Création du backup dans: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Sauvegarder les fichiers existants
echo "📦 Sauvegarde des fichiers existants..."
cp services/motor_service.py "$BACKUP_DIR/" 2>/dev/null && echo "   ✓ motor_service.py" || echo "   ⚠ motor_service.py non trouvé"
cp data/config.json "$BACKUP_DIR/" 2>/dev/null && echo "   ✓ config.json" || echo "   ⚠ config.json non trouvé"
cp core/tracking/adaptive_tracking.py "$BACKUP_DIR/" 2>/dev/null && echo "   ✓ adaptive_tracking.py" || echo "   ⚠ adaptive_tracking.py non trouvé"

echo ""
echo -e "${GREEN}✓ Backup créé${NC}"
echo ""

# Arrêter les services
echo "🛑 Arrêt des services..."
sudo ./start_web.sh stop 2>/dev/null || echo "   (services déjà arrêtés)"
sleep 2

# Copier les nouveaux fichiers
echo ""
echo "📋 Copie des nouveaux fichiers..."
cp "$SOURCE_DIR/motor_service.py" services/
echo "   ✓ services/motor_service.py"

cp "$SOURCE_DIR/config.json" data/
echo "   ✓ data/config.json"

cp "$SOURCE_DIR/adaptive_tracking.py" core/tracking/
echo "   ✓ core/tracking/adaptive_tracking.py"

# Créer le répertoire tests si nécessaire
if [ -d "$SOURCE_DIR/tests" ]; then
    echo ""
    echo "📋 Copie des scripts de test..."
    mkdir -p tests
    cp "$SOURCE_DIR/tests/"*.py tests/ 2>/dev/null || true
    cp "$SOURCE_DIR/tests/README.md" tests/ 2>/dev/null || true
    echo "   ✓ tests/"
fi

# Copier les fichiers de documentation
if [ -f "$SOURCE_DIR/CLAUDE.md" ]; then
    cp "$SOURCE_DIR/CLAUDE.md" .
    echo "   ✓ CLAUDE.md"
fi

if [ -f "$SOURCE_DIR/CHANGELOG.md" ]; then
    cp "$SOURCE_DIR/CHANGELOG.md" .
    echo "   ✓ CHANGELOG.md"
fi

echo ""
echo -e "${GREEN}✓ Fichiers copiés${NC}"

# Redémarrer les services
echo ""
echo "🚀 Redémarrage des services..."
sudo ./start_web.sh start
sleep 3

# Vérifier que les services tournent
echo ""
echo "🔍 Vérification des services..."
if pgrep -f "motor_service.py" > /dev/null; then
    echo -e "   ${GREEN}✓ Motor Service actif${NC}"
else
    echo -e "   ${RED}❌ Motor Service non démarré${NC}"
fi

if pgrep -f "ems22" > /dev/null; then
    echo -e "   ${GREEN}✓ Daemon encodeur actif${NC}"
else
    echo -e "   ${YELLOW}⚠ Daemon encodeur non détecté${NC}"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    DÉPLOIEMENT TERMINÉ                           ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "📋 Modifications apportées:"
echo "   • GOTO optimisé (rotation directe > 3°, feedback ≤ 3°)"
echo "   • JOG sans feedback (boutons manuels fluides)"
echo "   • FAST_TRACK supprimé (remplacé par CONTINUOUS)"
echo "   • CONTINUOUS.motor_delay = 0.00015s"
echo ""
echo "🧪 Tests recommandés:"
echo "   1. GOTO 90° → doit être fluide"
echo "   2. Boutons +10° → doit être fluide"
echo "   3. Tracking → doit fonctionner normalement"
echo ""
echo "🔄 Pour restaurer la version précédente:"
echo "   cp $BACKUP_DIR/* emplacements_respectifs/"
echo "   sudo ./start_web.sh restart"
echo ""
