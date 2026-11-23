#!/usr/bin/env bash
# Quick health report. Exit code is non-zero if something needs attention.
cd "$(dirname "$0")/.."
RC=0
say() { printf '%-28s %s\n' "$1" "$2"; }
H='Host: www.zerodayctf.com'
code=$(curl -s -o /dev/null -w '%{http_code}' -k -H "$H" https://127.0.0.1/healthcheck || true); say "healthcheck (https)" "$code"; [ "$code" = 200 ] || RC=1
code=$(curl -s -o /dev/null -w '%{http_code}' -k -H "$H" https://127.0.0.1/ || true); say "home page" "$code"; [ "$code" = 200 ] || RC=1
say "server clock" "$(curl -s -k -H "$H" https://127.0.0.1/server-time | head -c 120)"
exp=$(echo | openssl s_client -servername www.zerodayctf.com -connect 127.0.0.1:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
say "certificate expires" "${exp:-unknown}"
say "disk used (/)" "$(df -h / | awk 'NR==2 {print $5" of "$2}')"
say "memory free" "$(free -m | awk '/Mem:/ {print $7" MB available of "$2" MB"}')"
./deploy/compose.sh ps --format '{{.Service}}: {{.Status}}' 2>/dev/null | sed 's/^/  container /'
last=$(ls -1t "${BACKUP_DIR:-/var/backups/zerodayctf}"/db-*.sql.gz 2>/dev/null | head -1)
if [ -n "$last" ]; then age=$(( ($(date +%s) - $(stat -c %Y "$last")) / 3600 )); say "last database backup" "${age}h ago"; [ "$age" -lt 30 ] || RC=1; else say "last database backup" "NONE"; RC=1; fi
exit $RC
