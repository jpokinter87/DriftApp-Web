#!/bin/bash
# =============================================================================
# update_to_web.sh - Mise à jour vers la version Web de DriftApp
# =============================================================================
# Ce script:
# 1. Met à jour le code depuis GitHub (git pull)
# 2. Sauvegarde l'ancien fichier ems22d.service
# 3. Installe les nouveaux fichiers de service systemd
# 4. Démarre les services dans le bon ordre
#
# Usage: sudo ./update_to_web.sh
# =============================================================================

set -e  # Arrêter en cas d'erreur

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration - À ADAPTER SI NÉCESSAIRE
DRIFTAPP_DIR="/home/slenk/DriftApp"
BACKUP_DIR="/home/slenk/backups"
SERVICE_DIR="/etc/systemd/system"

# Fonction d'affichage
print_header() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}$1${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
}

print_step() {
    echo -e "${BLUE}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Vérification des privilèges root
if [ "$EUID" -ne 0 ]; then
    print_error "Ce script doit être exécuté en tant que root (sudo)"
    echo "Usage: sudo $0"
    exit 1
fi

# Début du script
print_header "MISE À JOUR VERS DRIFTAPP WEB"
echo ""
echo -e "  Répertoire: ${CYAN}$DRIFTAPP_DIR${NC}"
echo -e "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Vérifier que le répertoire existe
if [ ! -d "$DRIFTAPP_DIR" ]; then
    print_error "Répertoire $DRIFTAPP_DIR non trouvé!"
    echo "Vérifiez que DriftApp est cloné dans ce répertoire."
    exit 1
fi

# Créer le répertoire de backup si nécessaire
mkdir -p "$BACKUP_DIR"

# =============================================================================
# ÉTAPE 1: Arrêter les services existants
# =============================================================================
print_header "ÉTAPE 1: Arrêt des services"

print_step "Arrêt de motor_service.service (si actif)..."
if systemctl is-active --quiet motor_service.service 2>/dev/null; then
    systemctl stop motor_service.service
    print_success "motor_service.service arrêté"
else
    print_warning "motor_service.service n'était pas actif"
fi

print_step "Arrêt de ems22d.service (si actif)..."
if systemctl is-active --quiet ems22d.service 2>/dev/null; then
    systemctl stop ems22d.service
    print_success "ems22d.service arrêté"
else
    print_warning "ems22d.service n'était pas actif"
fi

# Petite pause pour libérer les GPIO
sleep 2

# =============================================================================
# ÉTAPE 2: Mise à jour du code
# =============================================================================
print_header "ÉTAPE 2: Mise à jour du code (git pull)"

cd "$DRIFTAPP_DIR"
print_step "Répertoire: $(pwd)"

# Sauvegarder l'état actuel
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
print_step "Commit actuel: $CURRENT_COMMIT"

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

# =============================================================================
# ÉTAPE 3: Sauvegarde de l'ancien service ems22d
# =============================================================================
print_header "ÉTAPE 3: Sauvegarde des fichiers de service"

BACKUP_TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

if [ -f "$SERVICE_DIR/ems22d.service" ]; then
    BACKUP_FILE="$BACKUP_DIR/ems22d.service.backup_$BACKUP_TIMESTAMP"
    cp "$SERVICE_DIR/ems22d.service" "$BACKUP_FILE"
    print_success "Sauvegarde: $BACKUP_FILE"

    # Créer aussi un lien vers la dernière sauvegarde
    ln -sf "$BACKUP_FILE" "$BACKUP_DIR/ems22d.service.last_backup"
    print_success "Lien créé: $BACKUP_DIR/ems22d.service.last_backup"
else
    print_warning "Pas de fichier ems22d.service existant à sauvegarder"
fi

# =============================================================================
# ÉTAPE 4: Installation des nouveaux fichiers de service
# =============================================================================
print_header "ÉTAPE 4: Installation des fichiers de service"

# Vérifier que les fichiers source existent
if [ ! -f "$DRIFTAPP_DIR/ems22d.service" ]; then
    print_error "Fichier $DRIFTAPP_DIR/ems22d.service non trouvé!"
    exit 1
fi

if [ ! -f "$DRIFTAPP_DIR/motor_service.service" ]; then
    print_error "Fichier $DRIFTAPP_DIR/motor_service.service non trouvé!"
    exit 1
fi

print_step "Copie de ems22d.service..."
cp "$DRIFTAPP_DIR/ems22d.service" "$SERVICE_DIR/"
print_success "ems22d.service installé"

print_step "Copie de motor_service.service..."
cp "$DRIFTAPP_DIR/motor_service.service" "$SERVICE_DIR/"
print_success "motor_service.service installé"

print_step "Rechargement de systemd..."
systemctl daemon-reload
print_success "Daemon systemd rechargé"

# =============================================================================
# ÉTAPE 5: Démarrage des services
# =============================================================================
print_header "ÉTAPE 5: Démarrage des services"

print_step "Activation et démarrage de ems22d.service..."
systemctl enable ems22d.service
systemctl start ems22d.service
sleep 2  # Attendre que l'encodeur soit prêt

if systemctl is-active --quiet ems22d.service; then
    print_success "ems22d.service actif"
else
    print_error "ems22d.service n'a pas démarré!"
    journalctl -u ems22d.service -n 10 --no-pager
    exit 1
fi

print_step "Activation et démarrage de motor_service.service..."
systemctl enable motor_service.service
systemctl start motor_service.service
sleep 3  # Attendre l'initialisation

if systemctl is-active --quiet motor_service.service; then
    print_success "motor_service.service actif"
else
    print_error "motor_service.service n'a pas démarré!"
    journalctl -u motor_service.service -n 10 --no-pager
    exit 1
fi

# =============================================================================
# RÉSUMÉ FINAL
# =============================================================================
print_header "MISE À JOUR TERMINÉE"

echo ""
echo -e "  ${GREEN}✓${NC} Code mis à jour depuis GitHub"
echo -e "  ${GREEN}✓${NC} Services systemd installés"
echo -e "  ${GREEN}✓${NC} ems22d.service: $(systemctl is-active ems22d.service)"
echo -e "  ${GREEN}✓${NC} motor_service.service: $(systemctl is-active motor_service.service)"
echo ""
echo -e "  ${CYAN}Sauvegarde:${NC} $BACKUP_DIR/ems22d.service.last_backup"
echo ""
echo -e "  ${YELLOW}Pour revenir à la version TUI:${NC}"
echo -e "  sudo $DRIFTAPP_DIR/scripts/revert_to_tui.sh"
echo ""
echo -e "  ${CYAN}Interface Web:${NC} http://$(hostname -I | awk '{print $1}'):8000"
echo ""
