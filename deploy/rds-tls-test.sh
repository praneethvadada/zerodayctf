#!/usr/bin/env bash
# Finds out which AWS certificate bundle works for YOUR RDS database, without logging in and without a password.
#   ./deploy/rds-tls-test.sh
# It checks the database's TLS certificate with OpenSSL against the global bundle and the bundle for your region.
set -uo pipefail
cd "$(dirname "$0")/.."
eval "$(python3 deploy/dburl.py)"
[ -n "${DB_HOST:-}" ] || { echo "DATABASE_URL is not set in .env"; exit 1; }
REGION=$(echo "$DB_HOST" | sed -E 's/.*\.([a-z0-9-]+)\.rds\.amazonaws\.com$/\1/')
mkdir -p .data/rds
echo "database: $DB_HOST   region: $REGION"
try() {  # $1 = label, $2 = bundle file
  printf '%-28s' "$1"
  out=$(echo | timeout 20 openssl s_client -starttls mysql -connect "$DB_HOST:$DB_PORT" -CAfile "$2" -verify_return_error -verify_hostname "$DB_HOST" 2>&1)
  code=$(echo "$out" | grep -m1 "Verify return code" | sed 's/^ *//')
  proto=$(echo "$out" | grep -m1 -E "Protocol *:" | sed 's/^ *//')
  echo "${code:-no TLS answer (blocked host or wrong endpoint?)}   ${proto}"
}
curl -fsSL -o .data/rds/test-global.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem && try "global bundle" .data/rds/test-global.pem
curl -fsSL -o .data/rds/test-region.pem "https://truststore.pki.rds.amazonaws.com/$REGION/$REGION-bundle.pem" && try "$REGION bundle" .data/rds/test-region.pem
echo
echo "Use the bundle that says 'Verify return code: 0 (ok)'. If it is the region one:  ./deploy/fetch-rds-ca.sh $REGION"
