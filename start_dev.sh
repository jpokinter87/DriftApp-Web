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

# Synchroniser les dépendances (crée le venv si nécessaire)
if command -v uv &> /dev/null; then
    uv sync --quiet 2>/dev/null || true
fi

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

cleanup_ipc_stale() {
    # Wipe les fichiers IPC traînants d'un run précédent (motor + cimier
    # command/status). Évite que l'UI lise un status `idle` figé d'une
    # ancienne session avant que les services aient eu le temps de publier
    # leur premier status frais. ems22_position.json est PRÉSERVÉ (cycle de
    # vie séparé via démon ems22d, pas géré par ce script).
    local stale_files=(
        "/dev/shm/motor_status.json"
        "/dev/shm/motor_command.json"
        "/dev/shm/cimier_status.json"
        "/dev/shm/cimier_command.json"
    )
    for f in "${stale_files[@]}"; do
        if [[ -f "$f" ]]; then
            rm -f "$f" 2>/dev/null && log_info "Cleanup IPC : $f supprimé"
        fi
    done
}

start_cimier_simulator() {
    if pgrep -f "cimier_simulator" > /dev/null; then
        log_info "Cimier Simulator déjà en cours d'exécution"
    else
        log_info "Démarrage du Cimier Simulator (Pico W simulé, port 8001)..."
        "$PYTHON" -m core.hardware.cimier_simulator --port 8001 --boot-delay 0.0 \
            > "$PROJECT_DIR/logs/cimier_simulator.log" 2>&1 &
        sleep 2
        if pgrep -f "cimier_simulator" > /dev/null; then
            log_info "Cimier Simulator démarré (PID: $(pgrep -f cimier_simulator))"
        else
            log_error "Échec du démarrage du Cimier Simulator"
            log_info "Vérifiez les logs: tail -f logs/cimier_simulator.log"
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

start_cimier_service() {
    if pgrep -f "services.cimier_service\|services/cimier_service.py" > /dev/null; then
        log_info "Cimier Service déjà en cours d'exécution"
        return
    fi

    # Lire cimier.enabled depuis data/config.json. Si false (défaut), le
    # cimier_service.py exit immédiatement (run_forever observe enabled=false
    # et termine). Inutile de le lancer dans ce cas — log un info clair.
    local cimier_enabled
    cimier_enabled=$("$PYTHON" -c "import json; print(json.load(open('$PROJECT_DIR/data/config.json')).get('cimier', {}).get('enabled', False))" 2>/dev/null)
    if [[ "$cimier_enabled" != "True" ]]; then
        log_warn "Cimier Service NON démarré : cimier.enabled=false dans data/config.json"
        log_info "  → Pour activer (smoke Phase 4 cimier complet) :"
        log_info "    éditer data/config.json → \"cimier.enabled\": true, puis ./start_dev.sh restart"
        return
    fi

    log_info "Démarrage du Cimier Service..."
    # En dev, cimier_service consomme cimier.host:port depuis data/config.json
    # qui pointe vers l'IP terrain (192.168.1.84). Il loguera des erreurs
    # réseau — non bloquant grâce au bypass staleness frontend Phase 4
    # (cf. ensureCimierOpenForTracking dashboard.js).
    "$PYTHON" -m services.cimier_service \
        > "$PROJECT_DIR/logs/cimier_service.log" 2>&1 &
    sleep 2
    if pgrep -f "services.cimier_service\|services/cimier_service.py" > /dev/null; then
        log_info "Cimier Service démarré (PID: $(pgrep -f 'services.cimier_service\|services/cimier_service.py'))"
    else
        log_error "Échec du démarrage du Cimier Service"
        log_info "Vérifiez les logs: tail -f logs/cimier_service.log"
    fi
}

start_django() {
    # Port configurable via env var, défaut 8000.
    local django_port="${DJANGO_PORT:-8000}"

    if pgrep -f "manage.py runserver" > /dev/null; then
        log_info "Django déjà en cours d'exécution"
        return
    fi

    # Pre-check : le port est-il déjà pris par un autre processus ?
    local port_user
    port_user=$(ss -tlnp 2>/dev/null | grep -E ":${django_port}\b" | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
    if [[ -n "$port_user" ]]; then
        local port_cmd
        port_cmd=$(ps -p "$port_user" -o cmd= 2>/dev/null | head -c 80)
        log_error "Port ${django_port} déjà occupé par PID ${port_user} : ${port_cmd}"
        log_info "  → Libérez le port ou lancez : DJANGO_PORT=8080 ./start_dev.sh start"
        return
    fi

    log_info "Démarrage de Django (port ${django_port})..."
    cd web
    nohup "$PYTHON" manage.py runserver "0.0.0.0:${django_port}" \
        > "$PROJECT_DIR/logs/django_runserver.log" 2>&1 &
    cd ..
    sleep 3
    if pgrep -f "manage.py runserver" > /dev/null; then
        log_info "Django démarré (PID: $(pgrep -f 'manage.py runserver') — http://localhost:${django_port})"
    else
        log_error "Échec du démarrage de Django"
        log_info "Voir : tail -f $PROJECT_DIR/logs/django_runserver.log"
    fi
}

stop_all() {
    log_info "Arrêt des services..."

    if pgrep -f "manage.py runserver" > /dev/null; then
        pkill -f "manage.py runserver"
        log_info "Django arrêté"
    fi

    if pgrep -f "services.cimier_service\|services/cimier_service.py" > /dev/null; then
        pkill -f "services.cimier_service\|services/cimier_service.py"
        log_info "Cimier Service arrêté"
    fi

    if pgrep -f "motor_service.py" > /dev/null; then
        pkill -f "motor_service.py"
        log_info "Motor Service arrêté"
    fi

    if pgrep -f "cimier_simulator" > /dev/null; then
        pkill -f "cimier_simulator"
        log_info "Cimier Simulator arrêté"
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

    # Cimier Simulator (Pico W simulé, dev seulement)
    if pgrep -f "cimier_simulator" > /dev/null; then
        echo -e "Cimier Simulator: ${GREEN}EN COURS${NC} (PID: $(pgrep -f cimier_simulator)) — http://localhost:8001"
    else
        echo -e "Cimier Simulator: ${RED}ARRÊTÉ${NC}"
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

    # Cimier Service
    if pgrep -f "services.cimier_service\|services/cimier_service.py" > /dev/null; then
        cimier_pid=$(pgrep -f 'services.cimier_service\|services/cimier_service.py')
        echo -e "Cimier Service:   ${GREEN}EN COURS${NC} (PID: $cimier_pid)"
        if [[ -f /dev/shm/cimier_status.json ]]; then
            cimier_state=$("$PYTHON" -c "import json; print(json.load(open('/dev/shm/cimier_status.json')).get('state', '?'))" 2>/dev/null)
            cimier_mode=$("$PYTHON" -c "import json; print(json.load(open('/dev/shm/cimier_status.json')).get('mode', '?'))" 2>/dev/null)
            echo "  État: $cimier_state | Mode auto: $cimier_mode"
        fi
    else
        # Distingue désactivé (config) vs arrêté (crash/non lancé).
        cimier_enabled=$("$PYTHON" -c "import json; print(json.load(open('$PROJECT_DIR/data/config.json')).get('cimier', {}).get('enabled', False))" 2>/dev/null)
        if [[ "$cimier_enabled" != "True" ]]; then
            echo -e "Cimier Service:   ${YELLOW}DÉSACTIVÉ${NC} (cimier.enabled=false dans config.json)"
        else
            echo -e "Cimier Service:   ${RED}ARRÊTÉ${NC}"
        fi
    fi

    # Django
    if pgrep -f "manage.py runserver" > /dev/null; then
        local dj_port
        dj_port=$(ps -p $(pgrep -f "manage.py runserver" | head -1) -o cmd= 2>/dev/null | grep -oE '0\.0\.0\.0:[0-9]+' | cut -d: -f2)
        dj_port="${dj_port:-8000}"
        echo -e "Django Web:       ${GREEN}EN COURS${NC} (PID: $(pgrep -f 'manage.py runserver' | head -1))"
        echo -e "  URL: ${CYAN}http://localhost:${dj_port}${NC}"
    else
        echo -e "Django Web:       ${RED}ARRÊTÉ${NC}"
    fi

    echo ""
}

# Point d'entrée
# Usage : ./start_dev.sh [start|stop|restart|status] [PORT]
# - PORT (optionnel) : port Django, défaut 8000. Ex: ./start_dev.sh start 8080.
#   Aussi exposé via env : DJANGO_PORT=8080 ./start_dev.sh start.
# Le port positional prend le pas sur DJANGO_PORT.
ACTION="${1:-start}"
if [[ -n "${2:-}" ]]; then
    export DJANGO_PORT="$2"
fi
DJANGO_PORT="${DJANGO_PORT:-8000}"

case "$ACTION" in
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
        cleanup_ipc_stale
        start_cimier_simulator
        start_motor_service
        start_cimier_service
        start_django

        echo ""
        echo -e "${GREEN}Services démarrés!${NC}"
        echo ""
        echo -e "Interface web: ${CYAN}http://localhost:${DJANGO_PORT}${NC}"
        echo ""
        echo "Commandes utiles:"
        echo "  ./start_dev.sh status              - Voir l'état des services"
        echo "  ./start_dev.sh stop                - Arrêter les services"
        echo "  ./start_dev.sh start 8080          - Lancer avec un port Django alternatif"
        echo "  tail -f logs/motor_service.log     - Logs Motor Service"
        echo "  tail -f logs/cimier_service.log    - Logs Cimier Service"
        echo "  tail -f logs/cimier_simulator.log  - Logs Cimier Simulator (Pico W simulé)"
        echo "  tail -f logs/django_runserver.log  - Logs Django (runserver)"
        echo ""
        status
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 2
        # Propage le port choisi (positional ou env DJANGO_PORT) au sous-appel.
        DJANGO_PORT="$DJANGO_PORT" "$0" start "$DJANGO_PORT"
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status} [PORT]"
        echo "  PORT : port Django (défaut 8000). Ex: $0 start 8080"
        exit 1
        ;;
esac
