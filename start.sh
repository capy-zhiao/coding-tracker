#!/usr/bin/env bash
# One-command launcher for the frontend and backend.
#   ./start.sh   start both, print today's queue, open the browser
#   Ctrl+C       stop both
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
API_PORT=8000
WEB_PORT=5173
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

green() { printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }

port_busy() { lsof -ti :"$1" >/dev/null 2>&1; }

cleanup() {
  echo
  yellow "Stopping services..."
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null
  wait 2>/dev/null
  green "Stopped. Run ./start.sh again next time."
}
trap cleanup EXIT INT TERM

echo "🧠 LeetCode Tracker"
echo "─────────────────────────────"

# ---------- dependency check (auto-installs on a fresh machine) ----------
if [[ ! -x "$BACKEND/.venv/bin/uvicorn" ]]; then
  yellow "First run: creating the Python virtualenv and installing dependencies..."
  python3 -m venv "$BACKEND/.venv" || { red "Could not create the venv - is python3 installed?"; exit 1; }
  "$BACKEND/.venv/bin/pip" install -q --upgrade pip
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt" || { red "Dependency install failed"; exit 1; }
fi

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  yellow "First run: installing frontend dependencies (this can take a minute)..."
  (cd "$FRONTEND" && npm install --silent) || { red "npm install failed"; exit 1; }
fi

if [[ ! -f "$BACKEND/tracker.db" ]]; then
  yellow "No database found - creating it and importing the problems..."
  (cd "$BACKEND" && ./.venv/bin/python migrate.py && ./.venv/bin/python seed_db.py) || {
    red "Database setup failed"; exit 1; }
else
  # Runs any new Alembic migrations, after taking a dated backup. Idempotent, and a no-op
  # once the schema is current. The backup matters: tracker.db is gitignored, so this
  # file is the only copy of your practice history.
  (cd "$BACKEND" && ./.venv/bin/python migrate.py) || {
    red "Schema migration failed - your data is untouched, see backend/.backups/"; exit 1; }
  # Refreshes pattern tags and picks up problems added to data/seed.json.
  (cd "$BACKEND" && ./.venv/bin/python seed_db.py >/dev/null)
fi

# ---------- backend ----------
if port_busy "$API_PORT"; then
  if curl -fsS "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
    green "Backend already running on $API_PORT"
  else
    red "Port $API_PORT is taken by something else - stop it and retry"
    red "   Check with: lsof -i :$API_PORT"
    exit 1
  fi
else
  (cd "$BACKEND" && ./.venv/bin/uvicorn app.main:app --port "$API_PORT" --reload) \
    > "$LOG_DIR/backend.log" 2>&1 &
  API_PID=$!
  printf "Starting backend"
  for _ in {1..30}; do
    curl -fsS "http://localhost:$API_PORT/health" >/dev/null 2>&1 && break
    printf "."; sleep 0.5
  done
  echo
  if curl -fsS "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
    green "Backend ready   http://localhost:$API_PORT/docs"
  else
    red "Backend failed to start - see $LOG_DIR/backend.log"; tail -20 "$LOG_DIR/backend.log"; exit 1
  fi
fi

# ---------- frontend ----------
if port_busy "$WEB_PORT"; then
  green "Frontend already running on $WEB_PORT"
else
  (cd "$FRONTEND" && npm run dev) > "$LOG_DIR/frontend.log" 2>&1 &
  WEB_PID=$!
  printf "Starting frontend"
  for _ in {1..40}; do
    curl -fsS -o /dev/null "http://localhost:$WEB_PORT/" 2>/dev/null && break
    printf "."; sleep 0.5
  done
  echo
  if curl -fsS -o /dev/null "http://localhost:$WEB_PORT/" 2>/dev/null; then
    green "Frontend ready  http://localhost:$WEB_PORT"
  else
    red "Frontend failed to start - see $LOG_DIR/frontend.log"; tail -20 "$LOG_DIR/frontend.log"; exit 1
  fi
fi

# ---------- open the browser and preview today's queue ----------
echo "─────────────────────────────"
curl -fsS "http://localhost:$API_PORT/review/today" 2>/dev/null | python3 -c "
import json, sys
try:
    q = json.load(sys.stdin)
except Exception:
    sys.exit()
print(f\"{q['date']}   {q['total_due']} due today\" + (f\" ({q['deferred']} deferred)\" if q['deferred'] else ''))
for name, key in [('Review  ', 'reviews'), ('New     ', 'new_problems'), ('Template', 'templates')]:
    items = q[key]
    if items:
        print(f'  {name}: ' + ' · '.join(f\"{i['problem']['number']} {i['problem']['title']}\" for i in items))
" 2>/dev/null

sleep 1
command -v open >/dev/null && open "http://localhost:$WEB_PORT"

echo "─────────────────────────────"
green "Ready.  http://localhost:$WEB_PORT"
echo "   (keep this window open; Ctrl+C stops both services)"
echo

wait
