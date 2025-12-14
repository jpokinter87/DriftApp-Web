#!/bin/bash
# Script de démarrage DriftApp Web
#
# Lance les 3 processus nécessaires:
# 1. Daemon encodeur (existant)
# 2. Motor Service (nouveau)
# 3. Django Web Server
#
# Usage:
#   ./start_web.sh          # Démarre tous les services
#   ./start_web.sh stop     # Arrête tous les services
#   ./start_web.sh status   # Vérifie l'état des services

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Ce script doit être exécuté en tant que root (sudo)"
        exit 1
    fi
}

start_encoder_daemon() {
    if pgrep -f "ems22d_calibrated.py" > /dev/null; then
        log_info "Daemon encodeur déjà en cours d'exécution"
    else
        log_info "Démarrage du daemon encodeur..."
        python3 ems22d_calibrated.py &
        sleep 2
        if pgrep -f "ems22d_calibrated.py" > /dev/null; then
            log_info "Daemon encodeur démarré"
        else
            log_error "Échec du démarrage du daemon encodeur"
        fi
    fi
}

start_motor_service() {
    if pgrep -f "motor_service.py" > /dev/null; then
        log_info "Motor Service déjà en cours d'exécution"
    else
        log_info "Démarrage du Motor Service..."
        python3 services/motor_service.py &
        sleep 2
        if pgrep -f "motor_service.py" > /dev/null; then
            log_info "Motor Service démarré"
        else
            log_error "Échec du démarrage du Motor Service"
        fi
    fi
}

start_django() {
    if pgrep -f "manage.py runserver" > /dev/null; then
        log_info "Django déjà en cours d'exécution"
    else
        log_info "Démarrage de Django..."
        cd web
        python3 manage.py runserver 0.0.0.0:8000 &
        cd ..
        sleep 2
        if pgrep -f "manage.py runserver" > /dev/null; then
            log_info "Django démarré sur http://localhost:8000"
        else
            log_error "Échec du démarrage de Django"
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

    if pgrep -f "ems22d_calibrated.py" > /dev/null; then
        pkill -f "ems22d_calibrated.py"
        log_info "Daemon encodeur arrêté"
    fi

    log_info "Tous les services arrêtés"
}

status() {
    echo "=== État des services DriftApp Web ==="
    echo

    if pgrep -f "ems22d_calibrated.py" > /dev/null; then
        echo -e "Daemon encodeur:  ${GREEN}EN COURS${NC}"
        if [[ -f /dev/shm/ems22_position.json ]]; then
            angle=$(python3 -c "import json; print(json.load(open('/dev/shm/ems22_position.json'))['angle'])" 2>/dev/null)
            echo "  Position: ${angle:-???}°"
        fi
    else
        echo -e "Daemon encodeur:  ${RED}ARRÊTÉ${NC}"
    fi

    if pgrep -f "motor_service.py" > /dev/null; then
        echo -e "Motor Service:    ${GREEN}EN COURS${NC}"
        if [[ -f /dev/shm/motor_status.json ]]; then
            status=$(python3 -c "import json; print(json.load(open('/dev/shm/motor_status.json'))['status'])" 2>/dev/null)
            echo "  État: ${status:-???}"
        fi
    else
        echo -e "Motor Service:    ${RED}ARRÊTÉ${NC}"
    fi

    if pgrep -f "manage.py runserver" > /dev/null; then
        echo -e "Django Web:       ${GREEN}EN COURS${NC}"
        echo "  URL: http://localhost:8000"
    else
        echo -e "Django Web:       ${RED}ARRÊTÉ${NC}"
    fi

    echo
}

# Point d'entrée
case "${1:-start}" in
    start)
        check_root
        log_info "Démarrage de DriftApp Web..."
        echo
        start_encoder_daemon
        start_motor_service
        start_django
        echo
        log_info "Tous les services démarrés!"
        log_info "Accédez à l'interface: http://raspberrypi:8000"
        echo
        status
        ;;
    stop)
        check_root
        stop_all
        ;;
    restart)
        check_root
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
