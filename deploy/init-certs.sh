#!/usr/bin/env bash
# Obtain a Let's Encrypt certificate for zerodayctf.com, www.zerodayctf.com, admin.zerodayctf.com
# (and www.admin.zerodayctf.com when its DNS record exists). Re-run it to add names to an existing certificate.
#
#   ./deploy/init-certs.sh you@example.com            real certificate
#   ./deploy/init-certs.sh you@example.com --staging  test run (not trusted, no rate limits)
#   ./deploy/init-certs.sh --self-signed-only         local testing only (self-signed)
#
# Prerequisites: DNS for both names already points at this server, and ports 80/443 are open.
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN=zerodayctf.com
NAMES=(-d zerodayctf.com -d www.zerodayctf.com -d admin.zerodayctf.com)
CONF=.data/certbot/conf
LIVE="$CONF/live/$DOMAIN"
SELF_ONLY=0; STAGING=""; EMAIL=""
for a in "$@"; do
  case "$a" in
    --self-signed-only) SELF_ONLY=1 ;;
    --staging) STAGING="--staging" ;;
    *@*) EMAIL="$a" ;;
  esac
done
if [ "$SELF_ONLY" -eq 0 ] && [ -z "$EMAIL" ]; then echo "Usage: $0 you@example.com [--staging]"; exit 1; fi

if [ "$SELF_ONLY" -eq 0 ]; then
  MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')
  for h in zerodayctf.com www.zerodayctf.com admin.zerodayctf.com; do
    DNSIP=$(dig +short "$h" | tail -n1)
    if [ "$DNSIP" != "$MYIP" ]; then
      echo "DNS check failed: $h resolves to '${DNSIP:-nothing}' but this server is $MYIP."
      echo "Fix the DNS A record (and wait a few minutes), then run this again."; exit 1
    fi
  done
  echo "DNS OK: all three names point to $MYIP"
  # optional extra name: only requested when its DNS record exists
  if [ "$(dig +short www.admin.zerodayctf.com | tail -n1)" = "$MYIP" ]; then
    NAMES+=(-d www.admin.zerodayctf.com); echo "Also including www.admin.zerodayctf.com"
  else
    echo "(www.admin.zerodayctf.com has no DNS record: skipped, that is fine)"
  fi
fi

mkdir -p "$CONF" .data/certbot/www
# certbot runs as root, so the certificate folders belong to root: use sudo for file checks/changes
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
if ! $SUDO test -f "$LIVE/fullchain.pem"; then
  echo "==> Creating a temporary self-signed certificate so nginx can start"
  $SUDO mkdir -p "$LIVE"
  $SUDO openssl req -x509 -nodes -newkey rsa:2048 -days 2 -subj "/CN=$DOMAIN" \
    -keyout "$LIVE/privkey.pem" -out "$LIVE/fullchain.pem" || { echo "Could not create the temporary certificate"; exit 1; }
  $SUDO touch "$LIVE/.temporary"
fi

echo "==> Starting the stack"
./deploy/compose.sh up -d --build
# nginx may be crash-looping from an earlier start without a certificate: restart it now that one exists
./deploy/compose.sh restart nginx
sleep 3
if [ -z "$(./deploy/compose.sh ps --status running --services | grep -x nginx)" ]; then
  echo "nginx is not running; see: ./deploy/compose.sh logs --tail 30 nginx"; exit 1
fi

if [ "$SELF_ONLY" -eq 1 ]; then echo "Self-signed certificate in place (local testing)."; exit 0; fi

# remove the temporary certificate, or an earlier --staging (test) certificate when asking for the real one
if $SUDO test -f "$LIVE/.temporary" || { [ -z "$STAGING" ] && $SUDO grep -qs "acme-staging" "$CONF/renewal/$DOMAIN.conf"; }; then
  echo "==> Removing the temporary/test certificate"
  $SUDO rm -rf "${CONF:?}/live/$DOMAIN" "${CONF:?}/archive/$DOMAIN" "${CONF:?}/renewal/$DOMAIN.conf"
fi

echo "==> Requesting the real certificate from Let's Encrypt ${STAGING:+(STAGING)}"
./deploy/compose.sh run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  --cert-name "$DOMAIN" --expand "${NAMES[@]}" --email "$EMAIL" --agree-tos --no-eff-email --non-interactive $STAGING

echo "==> Reloading nginx"
./deploy/compose.sh exec nginx nginx -s reload
echo "Done. https://www.zerodayctf.com should now work. Renewal runs automatically every 12 hours."
