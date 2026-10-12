#!/usr/bin/env bash
# Asks for the panel password and the Zabanyad API key and stores them in /opt/zabanyad-games/.env.
# Nothing typed here is shown on screen or saved anywhere else.
set -euo pipefail
ENV=/opt/zabanyad-games/.env
[ "$(id -u)" = 0 ] || { echo "Run with sudo / as root."; exit 1; }
[ -f "$ENV" ] || { echo "$ENV not found; run deploy/install.sh first."; exit 1; }

set_key() {  # set_key KEY VALUE  (value passed via env, not argv)
  KEY="$1" VALUE="$2" python3 - "$ENV" <<'PY'
import os, sys
path, key, value = sys.argv[1], os.environ["KEY"], os.environ["VALUE"]
lines = open(path, encoding="utf-8").read().splitlines()
out, done = [], False
for line in lines:
    if line.split("=", 1)[0].strip() == key:
        if not done:
            out.append(f"{key}={value}")
            done = True
        continue
    out.append(line)
if not done:
    out.append(f"{key}={value}")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
}

while true; do
  read -rsp "Panel password (min 8 characters, Enter = keep current): " P1; echo
  [ -z "$P1" ] && break
  read -rsp "Repeat the panel password: " P2; echo
  if [ "$P1" != "$P2" ]; then echo "Not the same, try again."; continue; fi
  if [ ${#P1} -lt 8 ]; then echo "Too short, try again."; continue; fi
  set_key ADMIN_PASSWORD "$P1"; echo "Panel password saved."; break
done

read -rsp "Zabanyad API key (X-Client-Secret, Enter = keep current): " SECRET; echo
if [ -n "$SECRET" ]; then
  set_key DISCOUNT_API_SECRET "$SECRET"
  set_key DISCOUNT_MODE live
  echo "API key saved; real discount codes are ON."
fi
unset P1 P2 SECRET

grep -q '^ADMIN_PASSWORD=.\+' "$ENV" || echo "Warning: no panel password yet; the panel will not open."
grep -q '^DISCOUNT_API_SECRET=.\+' "$ENV" || echo "Note: no API key yet; games give TEST codes (starting with T)."

if [ "${1:-}" != "--no-restart" ]; then
  systemctl restart zabanyad-games && echo "Service restarted."
fi
