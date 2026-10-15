#!/bin/sh
# Schedule backup.sh with busybox crond. crond starts jobs with an empty environment, so
# the settings they need (database connection, bucket, AWS credentials) are saved first.
set -eu
env | grep -E '^(PG[A-Z]+|BACKUP_[A-Z_]+|AWS_[A-Z_]+)=' | while IFS='=' read -r name value; do
  printf "export %s='%s'\n" "$name" "$(printf '%s' "$value" | sed "s/'/'\\\\''/g")"
done > /etc/backup.env
chmod 600 /etc/backup.env

schedule="${BACKUP_SCHEDULE:-15 3 * * *}"
echo "$schedule /usr/local/bin/backup.sh > /proc/1/fd/1 2>&1" > /etc/crontabs/root
echo "Backups scheduled at '$schedule' (UTC), bucket: ${BACKUP_BUCKET:-none, local copies only}"
exec crond -f -l 6
