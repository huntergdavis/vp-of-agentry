#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$root/data/telegram.json" ]]; then
  echo 'Run ./telegram-bridge setup first.' >&2
  exit 1
fi
# DS PR47 provides the one routing reader shared with the watchdog.
dunk_root="${DUNKING_SHEEP_DIR:-$root/../dunkingsheep}"
if [[ ! -f "$dunk_root/dunk_telegram_routing.py" ]]; then
  echo 'Install Dunking Sheep PR47 first; set DUNKING_SHEEP_DIR to that checkout.' >&2
  exit 1
fi
dunk_root="$(cd "$dunk_root" && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/vp-telegram.service" <<UNIT
[Unit]
Description=VP of Agentry private Telegram bridge
After=network-online.target vp-of-agentry.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$root
Environment="DUNKING_SHEEP_DIR=$dunk_root"
Environment="PYTHONPATH=$dunk_root"
ExecStart=$root/telegram-bridge run
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now vp-telegram.service
systemctl --user status vp-telegram.service --no-pager
