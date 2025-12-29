#!/bin/bash
# =============================================================================
# revert_to_tui.sh - Retour à la version TUI de DriftApp
# =============================================================================
# Ce script:
# 1. Arrête tous les services Web (motor_service et ems22d)
# 2. Supprime motor_service.service (n'existe pas en TUI, bloque GPIO)
# 3. Restaure la version TUI de ems22d.service (sauvegardée précédemment)
# 4. Redémarre ems22d.service
#
# Usage: sudo ./revert_to_tui.sh
# =============================================================================

set -e  # Arrêter en cas d'erreur

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration - À ADAPTER SI NÉCESSAIRE
BACKUP_DIR="/home/slenk/backups"
SERVICE_DIR="/etc/systemd/system"

# Fonction d'affichage
print_header() {
    echo ""
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║${NC}  ${BOLD}$1${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════════╝${NC}"
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
print_header "RETOUR À LA VERSION TUI"
echo ""
echo -e "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Vérifier qu'une sauvegarde existe
BACKUP_FILE="$BACKUP_DIR/ems22d.service.last_backup"
if [ ! -f "$BACKUP_FILE" ]; then
    print_error "Aucune sauvegarde trouvée!"
    echo ""
    echo "Le fichier $BACKUP_FILE n'existe pas."
    echo "Avez-vous exécuté update_to_web.sh au moins une fois?"
    echo ""

    # Proposer de lister les backups disponibles
    if [ -d "$BACKUP_DIR" ]; then
        echo "Sauvegardes disponibles dans $BACKUP_DIR:"
        ls -la "$BACKUP_DIR"/ems22d.service.backup_* 2>/dev/null || echo "  (aucune)"
    fi
    exit 1
fi

# Confirmation utilisateur
echo -e "${YELLOW}ATTENTION:${NC} Cette opération va:"
echo "  - Arrêter motor_service.service et ems22d.service"
echo "  - Supprimer motor_service.service (version Web)"
echo "  - Restaurer ems22d.service (version TUI)"
echo ""
read -p "Continuer? [o/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[OoYy]$ ]]; then
    print_warning "Opération annulée"
    exit 0
fi

# =============================================================================
# ÉTAPE 1: Arrêter tous les services
# =============================================================================
print_header "ÉTAPE 1: Arrêt des services"

print_step "Arrêt de motor_service.service..."
if systemctl is-active --quiet motor_service.service 2>/dev/null; then
    systemctl stop motor_service.service
    print_success "motor_service.service arrêté"
else
    print_warning "motor_service.service n'était pas actif"
fi

print_step "Désactivation de motor_service.service..."
if systemctl is-enabled --quiet motor_service.service 2>/dev/null; then
    systemctl disable motor_service.service
    print_success "motor_service.service désactivé"
fi

print_step "Arrêt de ems22d.service..."
if systemctl is-active --quiet ems22d.service 2>/dev/null; then
    systemctl stop ems22d.service
    print_success "ems22d.service arrêté"
else
    print_warning "ems22d.service n'était pas actif"
fi

# Petite pause pour libérer les GPIO
sleep 2

# =============================================================================
# ÉTAPE 2: Supprimer motor_service.service
# =============================================================================
print_header "ÉTAPE 2: Suppression de motor_service.service"

if [ -f "$SERVICE_DIR/motor_service.service" ]; then
    print_step "Suppression de $SERVICE_DIR/motor_service.service..."
    rm "$SERVICE_DIR/motor_service.service"
    print_success "motor_service.service supprimé"
else
    print_warning "motor_service.service n'existait pas"
fi

# =============================================================================
# ÉTAPE 3: Restaurer ems22d.service (version TUI)
# =============================================================================
print_header "ÉTAPE 3: Restauration de ems22d.service (TUI)"

print_step "Sauvegarde source: $BACKUP_FILE"

# Afficher les différences
echo ""
echo -e "${CYAN}Contenu de la sauvegarde TUI:${NC}"
cat "$BACKUP_FILE" | head -20
echo ""

print_step "Copie de la sauvegarde vers $SERVICE_DIR..."
cp "$BACKUP_FILE" "$SERVICE_DIR/ems22d.service"
print_success "ems22d.service restauré"

print_step "Rechargement de systemd..."
systemctl daemon-reload
print_success "Daemon systemd rechargé"

# =============================================================================
# ÉTAPE 4: Redémarrer ems22d.service
# =============================================================================
print_header "ÉTAPE 4: Démarrage de ems22d.service"

print_step "Activation et démarrage de ems22d.service..."
systemctl enable ems22d.service
systemctl start ems22d.service
sleep 2

if systemctl is-active --quiet ems22d.service; then
    print_success "ems22d.service actif"
else
    print_error "ems22d.service n'a pas démarré!"
    journalctl -u ems22d.service -n 10 --no-pager
    exit 1
fi

# =============================================================================
# RÉSUMÉ FINAL
# =============================================================================
print_header "RETOUR À LA VERSION TUI TERMINÉ"

echo ""
echo -e "  ${GREEN}✓${NC} motor_service.service supprimé"
echo -e "  ${GREEN}✓${NC} ems22d.service restauré (version TUI)"
echo -e "  ${GREEN}✓${NC} ems22d.service: $(systemctl is-active ems22d.service)"
echo ""
echo -e "  ${CYAN}Vous pouvez maintenant lancer l'application TUI:${NC}"
echo -e "  cd /home/slenk/Dome_v4_5 && python3 main.py"
echo ""
echo -e "  ${YELLOW}Pour revenir à la version Web:${NC}"
echo -e "  sudo /home/slenk/DriftApp/scripts/update_to_web.sh"
echo ""
