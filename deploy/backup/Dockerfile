# Nightly database backup: a pg_dump kept on a volume and, when BACKUP_BUCKET is set,
# copied to S3 (whose lifecycle rule expires old copies).
FROM alpine:3.20
RUN apk add --no-cache postgresql16-client aws-cli
COPY backup.sh entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
