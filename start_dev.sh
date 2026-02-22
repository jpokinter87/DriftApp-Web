#!/bin/bash
# Script de démarrage DriftApp Web - MODE DÉVELOPPEMENT
#
# Lance les services avec détection automatique du matériel.
# - Sur Raspberry Pi : mode production (GPIO réel)
# - Sur PC : mode simulation automatique
#
# Usage:
#   ./start_dev.sh          # Démarre les services
#   ./start_dev.sh stop     # Arrête tous les services

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Python du virtual environment
PYTHON="$PROJECT_DIR/.venv/bin/python"

# Vérifier que le venv existe
if [[ ! -f "$PYTHON" ]]; then
    echo -e "\033[0;31m[ERROR]\033[0m Virtual environment non trouvé!"
    echo "  → Exécutez d'abord: uv sync"
    exit 1
fi

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    # Vérifier Django
    if ! "$PYTHON" -c "import django" 2>/dev/null; then
        log_warn "Django non installé"
        echo ""
        echo -e "${CYAN}Installation des dépendances:${NC}"
        echo "  pip install django djangorestframework"
        echo "  # ou"
        echo "  pip install -r web/requirements.txt"
        echo ""
        read -p "Voulez-vous installer les dépendances maintenant? [O/n] " response
        if [[ "$response" =~ ^[Oo]?$ ]]; then
            pip install django djangorestframework
        else
            log_error "Django requis pour l'interface web"
            exit 1
        fi
    fi
}

start_motor_service() {
    if pgrep -f "motor_service.py" > /dev/null; then
        log_info "Motor Service déjà en cours d'exécution"
    else
        log_info "Démarrage du Motor Service (simulation)..."
        "$PYTHON" services/motor_service.py &
        sleep 2
        if pgrep -f "motor_service.py" > /dev/null; then
            log_info "Motor Service démarré (PID: $(pgrep -f motor_service.py))"
        else
            log_error "Échec du démarrage du Motor Service"
            log_info "Vérifiez les logs: tail -f logs/motor_service.log"
        fi
    fi
}

start_django() {
    if pgrep -f "manage.py runserver" > /dev/null; then
        log_info "Django déjà en cours d'exécution"
    else
        log_info "Démarrage de Django..."
        cd web
        "$PYTHON" manage.py runserver 0.0.0.0:8000 2>&1 &
        cd ..
        sleep 3
        if pgrep -f "manage.py runserver" > /dev/null; then
            log_info "Django démarré"
        else
            log_error "Échec du démarrage de Django"
            log_info "Essayez: cd web && $PYTHON manage.py runserver"
        fi
    fi
}

stop_all() {
    log_info "Arrêt des services..."

    if pgrep -f "manage.py runserver" > /dev/null; then
        pkill -f "manage.py runserver"
        log_info "Django arrêté"
    fi

    if pgrep -f "motor_service.py" > /dev/null; then
        pkill -f "motor_service.py"
        log_info "Motor Service arrêté"
    fi

    log_info "Tous les services arrêtés"
}

status() {
    echo ""
    echo "=== État des services DriftApp Web ==="
    echo ""

    # Détection du mode (Raspberry Pi ou non)
    if [[ -f /proc/device-tree/model ]] && grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
        echo -e "Mode:             ${YELLOW}PRODUCTION (Raspberry Pi)${NC}"
    else
        echo -e "Mode:             ${GREEN}SIMULATION (PC)${NC}"
    fi

    # Motor Service
    if pgrep -f "motor_service.py" > /dev/null; then
        echo -e "Motor Service:    ${GREEN}EN COURS${NC} (PID: $(pgrep -f motor_service.py))"
        if [[ -f /dev/shm/motor_status.json ]]; then
            status=$("$PYTHON" -c "import json; print(json.load(open('/dev/shm/motor_status.json')).get('status', '?'))" 2>/dev/null)
            pos=$("$PYTHON" -c "import json; print(f\"{json.load(open('/dev/shm/motor_status.json')).get('position', 0):.1f}\")" 2>/dev/null)
            echo "  État: $status | Position: ${pos}°"
        fi
    else
        echo -e "Motor Service:    ${RED}ARRÊTÉ${NC}"
    fi

    # Django
    if pgrep -f "manage.py runserver" > /dev/null; then
        echo -e "Django Web:       ${GREEN}EN COURS${NC}"
        echo -e "  URL: ${CYAN}http://localhost:8000${NC}"
    else
        echo -e "Django Web:       ${RED}ARRÊTÉ${NC}"
    fi

    echo ""
}

# Point d'entrée
case "${1:-start}" in
    start)
        echo ""
        echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║         DriftApp Web Interface         ║${NC}"
        echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
        echo ""

        # Détection automatique du mode
        if [[ -f /proc/device-tree/model ]] && grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
            log_info "Raspberry Pi détecté → Mode PRODUCTION"
        else
            log_info "PC détecté → Mode SIMULATION automatique"
        fi

        check_dependencies

        echo ""
        start_motor_service
        start_django

        echo ""
        echo -e "${GREEN}Services démarrés!${NC}"
        echo ""
        echo -e "Interface web: ${CYAN}http://localhost:8000${NC}"
        echo ""
        echo "Commandes utiles:"
        echo "  ./start_dev.sh status  - Voir l'état des services"
        echo "  ./start_dev.sh stop    - Arrêter les services"
        echo "  tail -f logs/motor_service.log - Logs Motor Service"
        echo ""
        status
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 2
        $0 start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
