#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/vp-of-agentry.service" <<UNIT
[Unit]
Description=VP of Agentry LAN desk
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$root
ExecStart=$root/run.sh
Restart=on-failure
RestartSec=3
UMask=0077

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now vp-of-agentry.service
systemctl --user status vp-of-agentry.service --no-pager
