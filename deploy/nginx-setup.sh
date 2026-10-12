#!/usr/bin/env bash
# Writes the nginx site for games.zabanyad.com: HTTPS when a certificate exists, otherwise HTTP only.
set -euo pipefail
APP=/opt/zabanyad-games
SVC=zabanyad-games
mkdir -p /var/www/letsencrypt /etc/nginx/snippets
cp "$APP/deploy/nginx-maps.conf" /etc/nginx/snippets/$SVC-maps.conf
cp "$APP/deploy/nginx-app.conf" /etc/nginx/snippets/$SVC-app.conf
if [ -f /etc/letsencrypt/live/games.zabanyad.com/fullchain.pem ]; then
  cp "$APP/deploy/nginx-ssl.conf" /etc/nginx/sites-available/$SVC
else
  cp "$APP/deploy/nginx.conf" /etc/nginx/sites-available/$SVC
fi
ln -sf /etc/nginx/sites-available/$SVC /etc/nginx/sites-enabled/$SVC
rm -f /etc/nginx/sites-enabled/default
nginx -t -q
systemctl reload nginx || systemctl restart nginx
