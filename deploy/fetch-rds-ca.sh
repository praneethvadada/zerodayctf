#!/usr/bin/env bash
# Downloads the AWS RDS certificate bundle so the app can verify its TLS connection to RDS.
#   ./deploy/fetch-rds-ca.sh              the global bundle (all regions)
#   ./deploy/fetch-rds-ca.sh ap-south-2   only the certificates of one region (smaller; use if the global one fails)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data/rds
REGION=${1:-}
if [ -n "$REGION" ]; then
  URL="https://truststore.pki.rds.amazonaws.com/$REGION/$REGION-bundle.pem"
else
  URL="https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"
fi
curl -fsSL -o .data/rds/global-bundle.pem "$URL"
grep -q "BEGIN CERTIFICATE" .data/rds/global-bundle.pem || { echo "Downloaded file is not a certificate bundle"; exit 1; }
echo "Saved .data/rds/global-bundle.pem from $URL ($(grep -c 'BEGIN CERTIFICATE' .data/rds/global-bundle.pem) certificates)"
