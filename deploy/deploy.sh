#!/usr/bin/env bash
# Update the running site to the latest code. Safe to run repeatedly.
#   ./deploy/deploy.sh            pull latest code, rebuild, restart, verify
#   ./deploy/deploy.sh rollback   go back to the previously deployed commit
set -euo pipefail
cd "$(dirname "$0")/.."

wait_healthy() {
  echo -n "Waiting for the app to become healthy"
  for _ in $(seq 1 60); do
    if curl -fsS -k -H 'Host: www.zerodayctf.com' https://127.0.0.1/healthcheck >/dev/null 2>&1 \
       || curl -fsS http://127.0.0.1/healthcheck >/dev/null 2>&1; then echo " OK"; return 0; fi
    echo -n "."; sleep 3
  done
  echo " FAILED"; ./deploy/compose.sh logs --tail 40 ctfd; return 1
}

if [ "${1:-}" = "rollback" ]; then
  [ -f .deploy_prev ] || { echo "No previous deployment recorded."; exit 1; }
  PREV=$(cat .deploy_prev); echo "Rolling back to $PREV"
  git checkout "$PREV"
else
  git rev-parse HEAD > .deploy_prev
  git pull --ff-only
fi

./deploy/compose.sh up -d --build
# nginx resolves the app's address only once at start: restart it so it never points at a replaced container
./deploy/compose.sh restart nginx
wait_healthy
git log --oneline -1
./deploy/compose.sh ps
