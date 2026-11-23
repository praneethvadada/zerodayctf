#!/usr/bin/env bash
# Wrapper: runs docker compose with the right production files.
# Uses AWS RDS automatically when DATABASE_URL is set in .env.
#   ./deploy/compose.sh ps | logs -f ctfd | exec ctfd ... | up -d --build
set -euo pipefail
cd "$(dirname "$0")/.."
FILES=(-f docker-compose.yml -f docker-compose.prod.yml)
if grep -q '^DATABASE_URL=' .env 2>/dev/null; then
  FILES+=(-f docker-compose.rds.yml)
fi
exec docker compose "${FILES[@]}" "$@"
