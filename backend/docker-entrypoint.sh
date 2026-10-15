#!/bin/sh
# Container start-up, the same steps start.sh runs locally. Both scripts are idempotent:
#   migrate.py  adds any new columns to an existing SQLite database, after a dated backup
#   seed_db.py  creates the tables on first start and adds problems new to data/
set -e
cd /app/backend
python migrate.py
python seed_db.py
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
