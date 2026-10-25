#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/vp-free-catalog.service" <<UNIT
[Unit]
Description=Watch free models on OpenRouter and OpenCode, update the context article
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$root
ExecStart=/usr/bin/python3 -I $root/tools/free_catalog.py
Environment=PATH=%h/.local/bin:/snap/bin:/usr/local/bin:/usr/bin:/bin
UMask=0077
UNIT
cat > "$unit_dir/vp-free-catalog.timer" <<UNIT
[Unit]
Description=Check the free model catalogue daily

[Timer]
OnCalendar=*-*-* 06:15:00
Persistent=true
RandomizedDelaySec=300
Unit=vp-free-catalog.service

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now vp-free-catalog.timer
systemctl --user list-timers vp-free-catalog.timer --no-pager
