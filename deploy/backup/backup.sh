#!/bin/sh
# One backup: a compressed custom-format pg_dump. The last 3 stay on the volume; with
# BACKUP_BUCKET set, each is also copied to S3. Run by cron, or by hand:
#   docker compose exec backup backup.sh
# Restore into the running database (replaces its contents):
#   docker compose exec -T backup sh -c 'pg_restore --clean --if-exists --no-owner -d "$PGDATABASE" /backups/<file>'
set -eu
[ -f /etc/backup.env ] && . /etc/backup.env

file="/backups/tracker-$(date -u +%Y-%m-%dT%H%MZ).dump"
pg_dump --format=custom --no-owner --file="$file"
echo "$(date -u +%FT%TZ) dumped $(du -h "$file" | cut -f1) to $file"

if [ -n "${BACKUP_BUCKET:-}" ]; then
  aws s3 cp "$file" "s3://$BACKUP_BUCKET/coding-tracker/$(basename "$file")" --only-show-errors
  echo "copied to s3://$BACKUP_BUCKET/coding-tracker/"
fi

ls -1t /backups/tracker-*.dump | tail -n +4 | xargs -r rm -f
