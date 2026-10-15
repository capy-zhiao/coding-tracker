#!/bin/sh
# Container start-up, the same steps start.sh runs locally. Both scripts are idempotent:
#   migrate.py  creates or upgrades the tables (Alembic), after a dated backup of SQLite
#   seed_db.py  adds problems new to data/
#   personal_seed.py  local mode only: problems solved in the notes start out due
set -e
cd /app/backend
python migrate.py
python seed_db.py
python personal_seed.py
# One worker: the demo account's daily rebuild runs in-process and must run once.
# --proxy-headers: Caddy in front sets X-Forwarded-For/Proto; nothing else can reach this
# port, so trusting any forwarder is safe.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*'
