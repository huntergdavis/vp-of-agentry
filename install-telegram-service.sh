#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$root/data/telegram.json" ]]; then
  echo 'Run ./telegram-bridge setup first.' >&2
  exit 1
fi
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
