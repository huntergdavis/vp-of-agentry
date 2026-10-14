#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/vp-ops-metrics.service" <<UNIT
[Unit]
Description=VP private operations metrics collection
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$root
ExecStart=$root/opsctl collect
UMask=0077
UNIT
cat > "$unit_dir/vp-ops-metrics.timer" <<UNIT
[Unit]
Description=Sample VP operations metrics every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Persistent=true
Unit=vp-ops-metrics.service

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now vp-ops-metrics.timer
systemctl --user start vp-ops-metrics.service
systemctl --user status vp-ops-metrics.timer --no-pager
