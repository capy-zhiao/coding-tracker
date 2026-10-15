# Backend image: FastAPI + SQLite. Build from the repository root, because seed_db.py
# reads the problem lists in data/:
#   docker build -f backend/Dockerfile -t coding-tracker-backend .
# docker-compose.yml at the root does this for you.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The timezone database: TIMEZONE (zoneinfo) and TZ both need it, otherwise "today" falls
# back to UTC and an evening session lands on the next day.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-prod.txt ./
RUN pip install -r requirements-prod.txt

COPY data /app/data
COPY backend /app/backend

# Run as an unprivileged user; /data is where the SQLite database (and its migration
# backups) live, mounted as a volume so they survive rebuilds.
RUN useradd --create-home --uid 10001 tracker \
    && mkdir -p /data \
    && chown tracker:tracker /data \
    && chmod +x /app/backend/docker-entrypoint.sh
USER tracker

ENV DATABASE_URL=sqlite:////data/tracker.db
EXPOSE 8000
ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
