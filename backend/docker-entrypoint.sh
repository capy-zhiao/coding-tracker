#!/bin/sh
# Container start-up, the same steps start.sh runs locally. Both scripts are idempotent:
#   migrate.py  creates or upgrades the tables (Alembic), after a dated backup of SQLite
#   seed_db.py  adds problems new to data/
set -e
cd /app/backend
python migrate.py
python seed_db.py
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
