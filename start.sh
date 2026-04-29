#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

find_compose() {
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        return 1
    fi
}

ACTION=${1:-help}

case $ACTION in

up|start)
    find_compose || error "docker compose not found"
    if [ ! -f .env ]; then
        cp .env.server.example .env
        warn "Created .env from .env.server.example — edit it, then re-run"
        exit 0
    fi
    echo "Building and starting all containers..."
    $COMPOSE_CMD up -d --build
    info "All services started"
    echo "  URL: http://localhost"
    echo "  Logs: bash start.sh logs"
    ;;

down|stop)
    find_compose || error "docker compose not found"
    $COMPOSE_CMD down
    info "All services stopped"
    ;;

restart)
    find_compose || error "docker compose not found"
    $COMPOSE_CMD restart
    info "All services restarted"
    ;;

logs)
    find_compose || error "docker compose not found"
    $COMPOSE_CMD logs -f
    ;;

ps|status)
    find_compose || error "docker compose not found"
    $COMPOSE_CMD ps
    ;;

build)
    find_compose || error "docker compose not found"
    $COMPOSE_CMD build --no-cache
    info "Images built"
    ;;

clean)
    find_compose || error "docker compose not found"
    read -p "WARNING: This will delete all containers and data! Confirm? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        $COMPOSE_CMD down -v --rmi all
        info "Cleanup complete"
    else
        echo "Cancelled"
    fi
    ;;

init)
    echo "=========================================="
    echo "  Bare-metal initialization"
    echo "=========================================="

    if ! command -v python3 &> /dev/null; then
        error "python3 not found — install Python 3.10+"
    fi
    info "Python3: $(python3 --version)"

    if [ ! -f .env ]; then
        cp .env.server.example .env
        warn "Created .env — edit database password and other settings"
    else
        info ".env already exists, skipping"
    fi

    if [ ! -d venv ]; then
        warn "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    source venv/bin/activate
    info "Virtual environment activated"

    warn "Installing Python dependencies..."
    pip install -r app/requirements.txt -q
    info "Dependencies installed"

    echo ""
    echo "=========================================="
    echo "  Initialization complete!"
    echo "  1. Edit .env (database, etc.)"
    echo "  2. Ensure MySQL and Redis are running"
    echo "  3. Run: bash start.sh run"
    echo "=========================================="
    ;;

run)
    if [ ! -d venv ]; then
        error "Run 'bash start.sh init' first"
    fi
    source venv/bin/activate
    info "Starting backend..."
    cd app && python main.py
    ;;

help|*)
    echo "Usage: bash start.sh <command>"
    echo ""
    echo "Docker deployment:"
    echo "  up/start   - Build and start all containers"
    echo "  down/stop  - Stop and remove containers"
    echo "  restart    - Restart all containers"
    echo "  logs       - View real-time logs"
    echo "  ps/status  - View container status"
    echo "  build      - Rebuild images"
    echo "  clean      - Remove all containers and data"
    echo ""
    echo "Bare-metal deployment:"
    echo "  init       - Initialize environment (venv + deps)"
    echo "  run        - Start the server"
    ;;

esac
