#!/bin/bash
# =============================================================================
# update_to_web.sh - Mise à jour DriftApp Web
# =============================================================================
# Ce script:
# 1. Met à jour le code depuis GitHub (git pull)
# 2. Synchronise les dépendances Python (uv sync)
# 3. Redémarre les services dans le bon ordre
#
# Peut être lancé de deux façons :
#   - Manuellement : sudo ./scripts/update_to_web.sh
#   - Depuis l'UI : détaché automatiquement (le script se relance en background)
#
# Usage: sudo ./scripts/update_to_web.sh [--background]
# =============================================================================

set -euo pipefail

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration — déduit automatiquement depuis l'emplacement du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIFTAPP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$DRIFTAPP_DIR/backups"
SERVICE_DIR="/etc/systemd/system"
LOG_FILE="$DRIFTAPP_DIR/logs/update.log"

# =============================================================================
# DÉTACHEMENT AUTOMATIQUE
# =============================================================================
# Si lancé depuis Django (pas de TTY, pas --background), se relancer en
# background pour survivre au redémarrage du service Django.
if [ "${1:-}" != "--background" ] && [ ! -t 0 ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
    nohup "$0" --background > "$LOG_FILE" 2>&1 &
    # Retourner immédiatement à Django avec succès
    echo "UPDATE_STARTED"
    exit 0
fi

# Si --background, on est le processus détaché — retirer le flag
shift 2>/dev/null || true

# Fonctions d'affichage
print_header() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}$1${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
}

print_step() { echo -e "${BLUE}▶${NC} $1"; }
print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

# Vérification des privilèges root
if [ "$EUID" -ne 0 ]; then
    print_error "Ce script doit être exécuté en tant que root (sudo)"
    echo "Usage: sudo $0"
    exit 1
fi

# Début du script
print_header "MISE À JOUR DRIFTAPP WEB"
echo ""
echo -e "  Répertoire: ${CYAN}$DRIFTAPP_DIR${NC}"
echo -e "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Vérifier que le répertoire existe
if [ ! -d "$DRIFTAPP_DIR/.git" ]; then
    print_error "Répertoire git $DRIFTAPP_DIR non trouvé!"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# =============================================================================
# ÉTAPE 1: Arrêter les services
# =============================================================================
print_header "ÉTAPE 1: Arrêt des services"

stop_service_robust() {
    local service=$1
    print_step "Arrêt de $service..."

    systemctl stop "$service" 2>/dev/null || true

    local attempts=0
    while systemctl is-active --quiet "$service" 2>/dev/null && [ $attempts -lt 10 ]; do
        sleep 1
        attempts=$((attempts + 1))
    done

    if systemctl is-active --quiet "$service" 2>/dev/null; then
        print_warning "Forçage de l'arrêt de $service..."
        systemctl kill "$service" 2>/dev/null || true
        sleep 2
    fi

    if systemctl is-active --quiet "$service" 2>/dev/null; then
        print_error "$service n'a pas pu être arrêté!"
        return 1
    else
        print_success "$service arrêté"
    fi
}

# Tuer les processus motor_service orphelins
if pgrep -f "motor_service.py" > /dev/null 2>&1; then
    print_warning "Processus motor_service.py orphelin, arrêt..."
    pkill -f "motor_service.py" 2>/dev/null || true
    sleep 2
fi

stop_service_robust "motor_service.service"
stop_service_robust "ems22d.service"

# Pause pour libérer les GPIO
print_step "Attente libération GPIO..."
sleep 3

# =============================================================================
# ÉTAPE 2: Mise à jour du code
# =============================================================================
print_header "ÉTAPE 2: Mise à jour du code (git pull)"

cd "$DRIFTAPP_DIR"
print_step "Répertoire: $(pwd)"

CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
print_step "Commit actuel: $CURRENT_COMMIT"

# Restaurer les permissions pour que git pull fonctionne
OWNER=$(stat -c '%U:%G' "$DRIFTAPP_DIR")
print_step "Restauration des permissions ($OWNER)..."
chown -R "$OWNER" "$DRIFTAPP_DIR" 2>/dev/null || true
print_success "Permissions restaurées"

# Nettoyer les modifications locales (config.json non touché par git pull
# car les changements config sont maintenant dans le dépôt)
if ! git diff --quiet 2>/dev/null; then
    print_step "Nettoyage des modifications locales..."
    git checkout -- . 2>/dev/null || true
    print_success "Modifications locales nettoyées"
fi

# Git pull
print_step "Téléchargement des mises à jour..."
if git pull origin main; then
    NEW_COMMIT=$(git rev-parse --short HEAD)
    if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
        print_success "Déjà à jour (commit: $NEW_COMMIT)"
    else
        print_success "Mis à jour: $CURRENT_COMMIT → $NEW_COMMIT"
    fi
else
    print_error "Échec du git pull"
    exit 1
fi

# Synchroniser les dépendances Python après mise à jour du code
print_step "Synchronisation des dépendances (uv sync --extra dev)..."
if command -v uv &> /dev/null; then
    if uv sync --extra dev 2>&1; then
        print_success "Dépendances synchronisées"
    else
        print_warning "Échec de uv sync — les dépendances peuvent être obsolètes"
    fi
else
    print_warning "uv non installé — synchronisation des dépendances ignorée"
fi

# Restaurer les permissions après le pull
print_step "Restauration des permissions après mise à jour ($OWNER)..."
chown -R "$OWNER" "$DRIFTAPP_DIR" 2>/dev/null || true
print_success "Permissions restaurées"

# =============================================================================
# ÉTAPE 3: Installation des fichiers de service
# =============================================================================
print_header "ÉTAPE 3: Installation des fichiers de service"

BACKUP_TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

# Sauvegarder les anciens services si présents
for svc in ems22d.service motor_service.service driftapp_web.service; do
    if [ -f "$SERVICE_DIR/$svc" ]; then
        cp "$SERVICE_DIR/$svc" "$BACKUP_DIR/${svc}.backup_$BACKUP_TIMESTAMP"
    fi
done
print_success "Services existants sauvegardés"

# Installer les nouveaux fichiers de service
for svc in ems22d.service motor_service.service driftapp_web.service; do
    if [ -f "$DRIFTAPP_DIR/$svc" ]; then
        cp "$DRIFTAPP_DIR/$svc" "$SERVICE_DIR/"
        print_success "$svc installé"
    else
        print_warning "$svc non trouvé dans le dépôt"
    fi
done

systemctl daemon-reload
print_success "Daemon systemd rechargé"

# =============================================================================
# ÉTAPE 4: Démarrage des services
# =============================================================================
print_header "ÉTAPE 4: Démarrage des services"

# Utilisateur réel pour les permissions
REAL_USER="${SUDO_USER:-$USER}"

# Ajuster les permissions des dossiers de données
print_step "Ajustement des permissions pour $REAL_USER..."
for dir in logs data web/data; do
    chown -R "$REAL_USER:$REAL_USER" "$DRIFTAPP_DIR/$dir" 2>/dev/null || true
done
chown "$REAL_USER:$REAL_USER" "$DRIFTAPP_DIR/web/db.sqlite3" 2>/dev/null || true
chown "$REAL_USER:$REAL_USER" "$DRIFTAPP_DIR/uv.lock" 2>/dev/null || true

# Démarrer encodeur
print_step "Démarrage ems22d.service..."
systemctl enable ems22d.service 2>/dev/null || true
systemctl start ems22d.service
sleep 2

if systemctl is-active --quiet ems22d.service; then
    print_success "ems22d.service actif"
else
    print_warning "ems22d.service n'a pas démarré"
    journalctl -u ems22d.service -n 5 --no-pager 2>/dev/null || true
fi

# Démarrer motor service
print_step "Démarrage motor_service.service..."
systemctl enable motor_service.service 2>/dev/null || true
systemctl start motor_service.service
sleep 3

if systemctl is-active --quiet motor_service.service; then
    print_success "motor_service.service actif"
else
    print_warning "motor_service.service n'a pas démarré"
    journalctl -u motor_service.service -n 5 --no-pager 2>/dev/null || true
fi

# Démarrer Django
print_step "Démarrage driftapp_web.service..."
systemctl enable driftapp_web.service 2>/dev/null || true
systemctl start driftapp_web.service
sleep 3

if systemctl is-active --quiet driftapp_web.service; then
    print_success "driftapp_web.service actif"
else
    print_error "driftapp_web.service n'a pas démarré!"
    journalctl -u driftapp_web.service -n 10 --no-pager 2>/dev/null || true
fi

# =============================================================================
# RÉSUMÉ FINAL
# =============================================================================
print_header "MISE À JOUR TERMINÉE"

echo ""
echo -e "  ${GREEN}✓${NC} Code mis à jour: $CURRENT_COMMIT → $(git rev-parse --short HEAD)"
echo -e "  ${GREEN}✓${NC} ems22d.service: $(systemctl is-active ems22d.service 2>/dev/null || echo 'inactive')"
echo -e "  ${GREEN}✓${NC} motor_service.service: $(systemctl is-active motor_service.service 2>/dev/null || echo 'inactive')"
echo -e "  ${GREEN}✓${NC} driftapp_web.service: $(systemctl is-active driftapp_web.service 2>/dev/null || echo 'inactive')"
echo ""
echo -e "  ${CYAN}Interface Web:${NC} http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000"
echo ""
