#!/bin/bash
# =============================================================================
# DriftApp - Script de déploiement vers Raspberry Pi
#
# Usage:
#   ./scripts/deploy.sh                    # Déploie vers pi@driftapp.local
#   ./scripts/deploy.sh pi@192.168.1.42    # Déploie vers une IP spécifique
#   ./scripts/deploy.sh --dry-run          # Simule sans exécuter
# =============================================================================

set -euo pipefail

PI_HOST="${1:-pi@driftapp.local}"
DRY_RUN=""

if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN="--dry-run"
    PI_HOST="${2:-pi@driftapp.local}"
    echo "=== MODE DRY-RUN (simulation) ==="
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="/home/pi/DriftApp"

echo "============================================"
echo "DriftApp - Déploiement"
echo "============================================"
echo "Source:  $PROJECT_DIR"
echo "Cible:   $PI_HOST:$REMOTE_DIR"
echo ""

# Vérifier la connexion SSH
echo "Vérification connexion SSH..."
if ! ssh -o ConnectTimeout=5 "$PI_HOST" "echo OK" > /dev/null 2>&1; then
    echo "ERREUR: Impossible de se connecter à $PI_HOST"
    echo "Vérifiez que le Pi est allumé et accessible."
    exit 1
fi
echo "Connexion OK"

# Synchroniser les fichiers
echo ""
echo "Synchronisation des fichiers..."
rsync -avz --delete $DRY_RUN \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='.paul/' \
    --exclude='.planning/' \
    --exclude='.claude/' \
    --exclude='.carl/' \
    --exclude='tests/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.venv/' \
    --exclude='.coverage' \
    --exclude='htmlcov/' \
    --exclude='.pytest_cache/' \
    --exclude='logs/*.log' \
    --exclude='db.sqlite3' \
    --exclude='*.egg-info/' \
    "$PROJECT_DIR/" "$PI_HOST:$REMOTE_DIR/"

if [ -n "$DRY_RUN" ]; then
    echo ""
    echo "=== DRY-RUN terminé (aucun fichier modifié) ==="
    exit 0
fi

# Redémarrer les services
echo ""
echo "Redémarrage des services..."
ssh "$PI_HOST" "sudo systemctl restart ems22d 2>/dev/null || true"
ssh "$PI_HOST" "cd $REMOTE_DIR && sudo ./start_web.sh restart 2>/dev/null || true"

# Vérifier le statut
echo ""
echo "Vérification des services..."
ssh "$PI_HOST" "systemctl is-active ems22d 2>/dev/null || echo 'ems22d: inactif'"

# Afficher la version déployée
VERSION=$(grep 'version = ' "$PROJECT_DIR/pyproject.toml" | head -1 | cut -d'"' -f2)
echo ""
echo "============================================"
echo "Déploiement terminé"
echo "Version: v$VERSION"
echo "Cible:   $PI_HOST"
echo "============================================"
