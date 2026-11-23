#!/usr/bin/env bash
# Restore a backup made by backup.sh.
#   ./deploy/restore.sh --db /var/backups/zerodayctf/db-XXXX.sql.gz --into ctfd_restore_test      (safe: scratch database)
#   ./deploy/restore.sh --db FILE --uploads FILE --overwrite-live                                   (replaces the live site!)
set -euo pipefail
cd "$(dirname "$0")/.."
DB_FILE=""; UP_FILE=""; INTO=""; LIVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --db) DB_FILE=$2; shift 2 ;;
    --uploads) UP_FILE=$2; shift 2 ;;
    --into) INTO=$2; shift 2 ;;
    --overwrite-live) LIVE=1; shift ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
done
[ -n "$DB_FILE" ] || { echo "Usage: $0 --db FILE.sql.gz [--into DBNAME | --overwrite-live] [--uploads FILE.tar.gz]"; exit 1; }
gzip -t "$DB_FILE"

eval "$(python3 deploy/dburl.py)"
LIVE_NAME=${DB_NAME:-ctfd}
if [ "$LIVE" -eq 1 ]; then TARGET=$LIVE_NAME; else TARGET=${INTO:?Give --into SCRATCH_DB_NAME, or --overwrite-live}; fi
if [ "$TARGET" = "$LIVE_NAME" ] && [ "$LIVE" -ne 1 ]; then echo "Refusing to touch the live database without --overwrite-live"; exit 1; fi

if [ "$LIVE" -eq 1 ]; then
  echo "This will REPLACE the live database '$TARGET' and uploads with the backup."
  read -r -p "Type RESTORE to continue: " ans; [ "$ans" = "RESTORE" ] || { echo "Cancelled."; exit 1; }
  ./deploy/compose.sh stop nginx ctfd
fi

sql() {  # run SQL read from stdin as the admin user
  if [ -n "${DB_HOST:-}" ]; then
    docker run --rm -i -e MYSQL_PWD="$DB_PASS" -v "$PWD/.data/rds/global-bundle.pem:/ca.pem:ro" mariadb:10.11 \
      mariadb --ssl-ca=/ca.pem --ssl-verify-server-cert -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$@"
  else
    ./deploy/compose.sh exec -T db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" "$@"' _ "$@"
  fi
}

echo "==> Recreating database $TARGET"
printf 'DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n' "$TARGET" "$TARGET" | sql
echo "==> Loading $DB_FILE"
gunzip -c "$DB_FILE" | sql "$TARGET"

if [ -n "$UP_FILE" ] && [ "$LIVE" -eq 1 ]; then
  echo "==> Restoring uploads"
  mkdir -p .data/CTFd && tar -xzf "$UP_FILE" -C .data/CTFd
fi
[ "$LIVE" -eq 1 ] && ./deploy/compose.sh up -d
echo "Restore finished into '$TARGET'."
