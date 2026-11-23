#!/usr/bin/env bash
# Downloads the AWS RDS certificate bundle so the app can verify its TLS connection to RDS.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data/rds
curl -fsSL -o .data/rds/global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
grep -q "BEGIN CERTIFICATE" .data/rds/global-bundle.pem || { echo "Downloaded file is not a certificate bundle"; exit 1; }
echo "Saved .data/rds/global-bundle.pem ($(grep -c 'BEGIN CERTIFICATE' .data/rds/global-bundle.pem) certificates)"
