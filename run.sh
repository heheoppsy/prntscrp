#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-python3}"
PIDS=()

cleanup() {
    printf "\n\033[0;33mShutting down...\033[0m\n"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    printf "\033[0;32mStopped.\033[0m\n"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill anything already on our ports
lsof -ti:8888 | xargs kill 2>/dev/null
lsof -ti:5173 | xargs kill 2>/dev/null
sleep 1

mkdir -p downloads log

# Install frontend deps if needed
if [ ! -d "frontend/node_modules" ]; then
    printf "\033[0;33m[setup]\033[0m Installing frontend dependencies...\n"
    (cd frontend && npm install)
fi

$PYTHON -c "from database import init_db; init_db()"

printf "\033[0;36m━━━ prntscrp ━━━\033[0m\n\n"

# Flask API
printf "\033[0;32m[api]\033[0m Starting on :8888\n"
$PYTHON run_web.py &
PIDS+=($!)

sleep 2

# SvelteKit
printf "\033[0;36m[web]\033[0m Starting on :5173\n"
cd frontend && npm run dev &
PIDS+=($!)
cd "$DIR"

sleep 2

printf "\n\033[0;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n"
printf "  Frontend:  \033[0;32mhttp://localhost:5173\033[0m\n"
printf "  API:       \033[2mhttp://127.0.0.1:8888\033[0m\n"
printf "\033[0;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n\n"

wait
