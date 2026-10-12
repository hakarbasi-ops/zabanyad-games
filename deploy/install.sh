#!/usr/bin/env bash
# Installs or updates Zabanyad games on Ubuntu 22.04/24.04. Run as root from the unzipped folder:
#   sudo bash deploy/install.sh
# Python packages come from deploy/wheels (no PyPI/Docker Hub needed). Data and .env survive updates.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/zabanyad-games
SVC=zabanyad-games
RUN_USER=zgames

[ "$(id -u)" = 0 ] || { echo "Run with sudo / as root."; exit 1; }

echo "==> System packages"
NEED=()
command -v nginx >/dev/null || NEED+=(nginx)
python3 -c "import venv, ensurepip" 2>/dev/null || NEED+=(python3-venv)
if [ ${#NEED[@]} -gt 0 ]; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${NEED[@]}"
fi

id "$RUN_USER" >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin "$RUN_USER"

echo "==> Copying the app to $APP"
mkdir -p "$APP/data" "$APP/backups"
rm -rf "$APP/app" "$APP/static" "$APP/deploy"
cp -r "$SRC/app" "$SRC/static" "$SRC/deploy" "$APP/"
cp "$SRC/requirements.txt" "$SRC/.env.example" "$APP/"
find "$APP/app" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "==> Python packages (offline)"
[ -x "$APP/.venv/bin/python" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --no-index --find-links "$APP/deploy/wheels" -r "$APP/requirements.txt"

if [ ! -f "$APP/.env" ]; then
  cp "$APP/.env.example" "$APP/.env"
  chmod 600 "$APP/.env"
  echo "==> First install: setting the panel password and the Zabanyad API key"
  bash "$APP/deploy/set-credentials.sh" --no-restart
fi
chown -R "$RUN_USER:$RUN_USER" "$APP/data" "$APP/backups"
chown root:"$RUN_USER" "$APP/.env"
chmod 640 "$APP/.env"

echo "==> Service"
cp "$APP/deploy/zabanyad-games.service" /etc/systemd/system/$SVC.service
systemctl daemon-reload
systemctl enable -q $SVC
systemctl restart $SVC

echo "==> nginx"
bash "$APP/deploy/nginx-setup.sh"

echo "==> Daily database backup (03:30, keeps 14 days)"
cat > /etc/cron.d/$SVC-backup <<CRON
30 3 * * * $RUN_USER $APP/.venv/bin/python $APP/deploy/backup.py $APP/data/games.db $APP/backups 14
CRON

sleep 2
if curl -fsS http://127.0.0.1:8000/healthz >/dev/null; then
  echo
  echo "Done. Version $(cat "$APP/app/VERSION")."
  if [ -d /etc/letsencrypt/live/games.zabanyad.com ]; then P=https; else P=http; fi
  echo "  Games: $P://games.zabanyad.com/"
  echo "  Panel: $P://games.zabanyad.com/admin"
  [ "$P" = http ] && echo "  HTTPS: sudo bash $APP/deploy/enable-https.sh"
else
  echo "The service did not answer. Last log lines:"
  journalctl -u $SVC -n 30 --no-pager
  exit 1
fi
