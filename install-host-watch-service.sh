#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/vp-host-watch.service" <<UNIT
[Unit]
Description=VP host temporary storage and load watch

[Service]
Type=oneshot
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/host_watch.py
UMask=0077
UNIT
cat > "$unit_dir/vp-host-watch.timer" <<UNIT
[Unit]
Description=Check temporary storage and host load every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=5s
Persistent=true
Unit=vp-host-watch.service

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now vp-host-watch.timer
systemctl --user start vp-host-watch.service
systemctl --user status vp-host-watch.timer --no-pager
