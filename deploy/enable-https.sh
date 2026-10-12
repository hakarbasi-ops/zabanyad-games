#!/usr/bin/env bash
# Gets a free Let's Encrypt certificate for games.zabanyad.com and switches nginx to HTTPS. Renews by itself.
#   sudo bash /opt/zabanyad-games/deploy/enable-https.sh
# Way 1 (default): the HTTP check. Needs games.zabanyad.com -> this server, and port 80 open from abroad.
# Way 2 (if way 1 fails): DNS check through Cloudflare with an API token (works even if foreign traffic is blocked).
set -uo pipefail
DOMAIN=games.zabanyad.com
APP=/opt/zabanyad-games
[ "$(id -u)" = 0 ] || { echo "Run with sudo / as root."; exit 1; }

echo "==> Installing certbot"
command -v certbot >/dev/null || { apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q certbot; } || {
  echo "Could not install certbot (apt). Check the server's internet access."; exit 1; }

mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/bin/sh
systemctl reload nginx
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

read -rp "Email for certificate notices (Enter = none): " EMAIL
if [ -n "$EMAIL" ]; then MAIL=(-m "$EMAIL"); else MAIL=(--register-unsafely-without-email); fi

bash "$APP/deploy/nginx-setup.sh"   # make sure /.well-known is served on port 80

echo "==> Way 1: HTTP check"
if certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" --agree-tos --non-interactive "${MAIL[@]}"; then
  OK=1
else
  OK=0
  echo
  echo "The HTTP check failed. Usual reasons: the DNS record of $DOMAIN does not point to this server yet,"
  echo "or traffic from outside Iran cannot reach this server."
  read -rp "Try way 2 (DNS check through a Cloudflare API token)? [y/N] " ANS
  if [[ "$ANS" =~ ^[Yy] ]]; then
    apt-get install -y -q python3-certbot-dns-cloudflare || { echo "Could not install the Cloudflare plugin."; exit 1; }
    echo "Create a token in Cloudflare: My Profile > API Tokens > Create Token > template 'Edit zone DNS',"
    echo "zone = zabanyad.com. Paste it below (not shown on screen)."
    read -rsp "Cloudflare API token: " CFT; echo
    install -d -m 700 /root/.secrets
    umask 077
    printf 'dns_cloudflare_api_token = %s\n' "$CFT" > /root/.secrets/cloudflare.ini
    unset CFT
    certbot certonly --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
      --dns-cloudflare-propagation-seconds 30 -d "$DOMAIN" --agree-tos --non-interactive "${MAIL[@]}" && OK=1
  fi
fi

if [ "$OK" = 1 ]; then
  bash "$APP/deploy/nginx-setup.sh"
  echo
  echo "HTTPS is on: https://$DOMAIN/  (renews automatically)"
  echo "If Cloudflare's orange cloud is on for $DOMAIN, set its SSL mode to 'Full (strict)'."
else
  echo "No certificate yet; the site stays on HTTP. Send the messages above to support."
  exit 1
fi
