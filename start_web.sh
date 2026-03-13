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

# Python du virtual environment
PYTHON="$PROJECT_DIR/.venv/bin/python"

# Vérifier que le venv existe
if [[ ! -f "$PYTHON" ]]; then
    echo -e "\033[0;31m[ERROR]\033[0m Virtual environment non trouvé!"
    echo "  → Exécutez d'abord: uv sync"
    exit 1
fi

# Utilisateur qui a lancé sudo (pour les permissions des fichiers)
REAL_USER="${SUDO_USER:-$USER}"

# Créer le dossier logs avec les bonnes permissions
setup_logs() {
    if [[ ! -d "$PROJECT_DIR/logs" ]]; then
        mkdir -p "$PROJECT_DIR/logs"
    fi
    # S'assurer que l'utilisateur peut écrire dans logs (pas root)
    chown -R "$REAL_USER:$REAL_USER" "$PROJECT_DIR/logs" 2>/dev/null || true
}

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

check_encoder_daemon() {
    # Le daemon encodeur est géré par systemd (ems22d.service)
    # On vérifie juste qu'il tourne, on ne le démarre pas manuellement
    if systemctl is-active --quiet ems22d 2>/dev/null; then
        log_info "Daemon encodeur (systemd): EN COURS"
        return 0
    elif pgrep -f "ems22d_calibrated.py" > /dev/null; then
        log_warn "Daemon encodeur: en cours (mode manuel, pas systemd)"
        return 0
    else
        log_error "Daemon encodeur NON ACTIF!"
        log_info "  → Démarrer avec: sudo systemctl start ems22d"
        log_info "  → Ou manuellement: sudo python3 ems22d_calibrated.py &"
        return 1
    fi
}

start_motor_service() {
    if pgrep -f "motor_service.py" > /dev/null; then
        log_info "Motor Service déjà en cours d'exécution"
    else
        log_info "Démarrage du Motor Service..."
        "$PYTHON" services/motor_service.py &
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
        "$PYTHON" web/manage.py runserver 0.0.0.0:8000 &
        sleep 2
        if pgrep -f "manage.py runserver" > /dev/null; then
            log_info "Django démarré sur http://localhost:8000"
        else
            log_error "Échec du démarrage de Django"
        fi
    fi
}

stop_all() {
    log_info "Arrêt des services DriftApp Web..."

    if pgrep -f "manage.py runserver" > /dev/null; then
        pkill -f "manage.py runserver"
        log_info "Django arrêté"
    fi

    if pgrep -f "motor_service.py" > /dev/null; then
        pkill -f "motor_service.py"
        log_info "Motor Service arrêté"
    fi

    # NOTE: Le daemon encodeur (ems22d) est géré par systemd
    # On ne l'arrête PAS ici - il doit continuer à tourner
    log_info "Services DriftApp Web arrêtés"
    log_info "(Daemon encodeur ems22d non touché - géré par systemd)"
}

status() {
    echo "=== État des services DriftApp Web ==="
    echo

    # Daemon encodeur (systemd)
    if systemctl is-active --quiet ems22d 2>/dev/null; then
        echo -e "Daemon encodeur:  ${GREEN}EN COURS${NC} (systemd)"
        if [[ -f /dev/shm/ems22_position.json ]]; then
            angle=$(python3 -c "import json; print(f\"{json.load(open('/dev/shm/ems22_position.json'))['angle']:.2f}\")" 2>/dev/null)
            echo "  Position: ${angle:-???}°"
        fi
    elif pgrep -f "ems22d_calibrated.py" > /dev/null; then
        echo -e "Daemon encodeur:  ${YELLOW}EN COURS${NC} (manuel)"
        if [[ -f /dev/shm/ems22_position.json ]]; then
            angle=$(python3 -c "import json; print(f\"{json.load(open('/dev/shm/ems22_position.json'))['angle']:.2f}\")" 2>/dev/null)
            echo "  Position: ${angle:-???}°"
        fi
    else
        echo -e "Daemon encodeur:  ${RED}ARRÊTÉ${NC}"
        echo "  → sudo systemctl start ems22d"
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

        # Préparer le dossier logs avec les bonnes permissions
        setup_logs

        # Vérifier que le daemon encodeur tourne (géré par systemd)
        check_encoder_daemon
        encoder_ok=$?

        start_motor_service
        start_django
        echo

        if [[ $encoder_ok -eq 0 ]]; then
            log_info "Tous les services sont opérationnels!"
        else
            log_warn "Services démarrés mais daemon encodeur absent"
        fi
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

        # Relancer directement (pas via $0 pour garder le contexte sudo)
        log_info "Démarrage de DriftApp Web..."
        echo
        setup_logs
        check_encoder_daemon
        encoder_ok=$?
        start_motor_service
        start_django
        echo
        if [[ $encoder_ok -eq 0 ]]; then
            log_info "Tous les services sont opérationnels!"
        else
            log_warn "Services démarrés mais daemon encodeur absent"
        fi
        log_info "Accédez à l'interface: http://raspberrypi:8000"
        echo
        status
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
