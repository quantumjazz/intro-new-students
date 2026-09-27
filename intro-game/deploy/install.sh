#!/usr/bin/env bash
# One-time install on the Ubuntu laptop, run with sudo from the clone:
#
#   sudo bash /home/victor/apps/intro-new-students/intro-game/deploy/install.sh
#
# Installs the intro-game service on 127.0.0.1:8004 and adds
# intro.visiometrica.com to the Cloudflare Tunnel `laptop-server`.
# Safe to run again: it skips what is already in place.
# The DNS record is separate and needs no sudo:
#   cloudflared tunnel route dns laptop-server intro.visiometrica.com
set -euo pipefail

HOST=intro.visiometrica.com
PORT=8004
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it with sudo." >&2
  exit 1
fi

# 1. The service.
install -m 644 "$HERE/intro-game.service" /etc/systemd/system/intro-game.service
systemctl daemon-reload
systemctl enable intro-game
systemctl restart intro-game
echo "Service: intro-game on 127.0.0.1:$PORT"

# 2. The tunnel. Edit the config the cloudflared unit actually reads (there is
#    a leftover ~/.cloudflared/config.yml that is not used).
CONFIG="$(systemctl cat cloudflared | sed -n 's/.*--config[ =]\([^ ]*\).*/\1/p' | head -n1)"
CONFIG="${CONFIG:-/etc/cloudflared/config.yml}"
if grep -q "hostname: $HOST" "$CONFIG"; then
  echo "Tunnel: $HOST is already in $CONFIG"
else
  BACKUP="$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
  cp -p "$CONFIG" "$BACKUP"
  # Insert after the last hostname entry, so the catch-all stays last.
  python3 - "$CONFIG" "$HOST" "$PORT" <<'PY'
import sys
path, host, port = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
last = max(i for i, line in enumerate(lines) if line.lstrip().startswith("- hostname:"))
indent = lines[last][: len(lines[last]) - len(lines[last].lstrip())]
end = last + 1
while end < len(lines) and lines[end].strip() and not lines[end].lstrip().startswith(("-", "#")):
    end += 1
lines[end:end] = [f"{indent}- hostname: {host}\n", f"{indent}  service: http://127.0.0.1:{port}\n"]
open(path, "w", encoding="utf-8").writelines(lines)
PY
  if ! cloudflared tunnel --config "$CONFIG" ingress validate >/dev/null; then
    cp -p "$BACKUP" "$CONFIG"
    echo "The new tunnel config did not validate; restored $BACKUP. Nothing restarted." >&2
    exit 1
  fi
  systemctl restart cloudflared
  echo "Tunnel: added $HOST -> 127.0.0.1:$PORT (backup: $BACKUP)"
fi

# 3. Check. The server needs a moment before it listens.
sleep 3
curl -fsS "http://127.0.0.1:$PORT/api/health" && echo
