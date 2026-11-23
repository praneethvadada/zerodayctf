#!/usr/bin/env bash
# Backup the database (logical dump) and the uploaded files.
#   ./deploy/backup.sh
# Env: BACKUP_DIR (default /var/backups/zerodayctf)  KEEP_DAYS (default 14)
#      BACKUP_S3_URI (optional, e.g. s3://my-bucket/zerodayctf, needs the aws CLI and an IAM role)
# With RDS, AWS also keeps automated snapshots; this dump is an extra, portable copy.
set -euo pipefail
cd "$(dirname "$0")/.."
BACKUP_DIR=${BACKUP_DIR:-/var/backups/zerodayctf}
KEEP_DAYS=${KEEP_DAYS:-14}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACKUP_DIR"
DB_FILE="$BACKUP_DIR/db-$STAMP.sql.gz"
UP_FILE="$BACKUP_DIR/uploads-$STAMP.tar.gz"

eval "$(python3 deploy/dburl.py)"
DUMP_OPTS=(--single-transaction --quick --routines --triggers --skip-lock-tables)
if [ -n "${DB_HOST:-}" ]; then
  echo "==> Dumping database $DB_NAME from RDS ($DB_HOST)"
  docker run --rm -e MYSQL_PWD="$DB_PASS" -v "$PWD/.data/rds/global-bundle.pem:/ca.pem:ro" mariadb:10.11 \
    mariadb-dump "${DUMP_OPTS[@]}" --ssl-ca=/ca.pem --ssl-verify-server-cert -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME" \
    | gzip > "$DB_FILE.part"
else
  echo "==> Dumping database from the local MariaDB container"
  ./deploy/compose.sh exec -T db sh -c 'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --quick --routines --triggers --skip-lock-tables ctfd' \
    | gzip > "$DB_FILE.part"
fi
gzip -t "$DB_FILE.part"
gunzip -c "$DB_FILE.part" | tail -n 3 | grep -q "Dump completed" || { echo "Dump looks incomplete, aborting"; rm -f "$DB_FILE.part"; exit 1; }
mv "$DB_FILE.part" "$DB_FILE"

echo "==> Archiving uploaded files"
if [ -d .data/CTFd/uploads ]; then tar -czf "$UP_FILE" -C .data/CTFd uploads; else tar -czf "$UP_FILE" --files-from /dev/null; fi

( cd "$BACKUP_DIR" && sha256sum "$(basename "$DB_FILE")" "$(basename "$UP_FILE")" >> SHA256SUMS )
echo "db      : $DB_FILE ($(du -h "$DB_FILE" | cut -f1))"
echo "uploads : $UP_FILE ($(du -h "$UP_FILE" | cut -f1))"

if [ -n "${BACKUP_S3_URI:-}" ] && command -v aws >/dev/null 2>&1; then
  echo "==> Copying to $BACKUP_S3_URI"
  aws s3 cp "$DB_FILE" "$BACKUP_S3_URI/" --only-show-errors
  aws s3 cp "$UP_FILE" "$BACKUP_S3_URI/" --only-show-errors
fi

find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'db-*.sql.gz' -o -name 'uploads-*.tar.gz' \) -mtime +"$KEEP_DAYS" -delete
echo "Backup finished."
