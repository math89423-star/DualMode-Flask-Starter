#!/bin/bash

cleanup() {
    echo ""
    echo "Stopping all services..."
    pkill -f "gunicorn" || true
    pkill -f "run_worker.py" || true
    echo "All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

pkill -f "gunicorn" || true
pkill -f "run_worker.py" || true
pkill -f "rq worker" || true

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_ROOT"

export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT

echo "------------------------------------------"
echo "DualMode Flask Starter - Backend starting..."
echo "------------------------------------------"

if [ -z "$REDIS_URL" ]; then
    echo "[ERROR] REDIS_URL environment variable not found"
    exit 1
fi

echo "[INFO] Initializing database..."
python -m backend.model.init_db
if [ $? -eq 0 ]; then
    echo "[OK] Database initialized"
else
    echo "[ERROR] Database initialization failed"
    exit 1
fi

echo "[INFO] Starting web server..."
gunicorn -k gthread -w 4 --threads 50 -b 0.0.0.0:5000 "main:app" 2>&1 | tee -a web.log &
WEB_PID=$!
echo "[OK] Web server started (PID: $WEB_PID) on port 5000"

WORKER_COUNT=4
echo "[INFO] Redis: $REDIS_URL"
echo "[INFO] Queue: tasks"
echo "[INFO] Starting $WORKER_COUNT workers..."

for i in $(seq 1 $WORKER_COUNT)
do
    python run_worker.py 2>&1 | tee -a worker_$i.log &
    sleep 0.5
done

echo "[OK] $WORKER_COUNT workers started"
echo "=========================================="
echo "Backend fully started!"
echo "=========================================="

wait
