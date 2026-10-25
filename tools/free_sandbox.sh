#!/usr/bin/env bash
# Run an UNTRUSTED free-model process in an ALLOWLISTED filesystem.
#   POOLRAD_REPO=/path/to/repo tools/free_sandbox.sh OUTDIR command [args...]
# Inside: /usr and /etc read-only, a private empty HOME and /tmp, no /run (so no host control
# sockets: not the dunkingsheep daemon, not systemd, not the display), the subject repo READ-ONLY,
# and OUTDIR as the only writable place. pi gets a throwaway config dir whose auth.json holds
# ONLY the openrouter credential (the user's anthropic/openai/opencode credentials are not copied).
# Residual risk, stated plainly: (1) the openrouter key is readable by the model - use a dedicated
# low-value key for free runs; (2) the network namespace is shared (the models need the API), so
# abstract-namespace unix sockets of the host remain reachable; nothing in this fleet uses them.
set -euo pipefail
OUT="${1:?output dir}"; shift
REPO="${POOLRAD_REPO:?POOLRAD_REPO must name the subject repo}"
mkdir -p "$OUT"
AGENT="$(mktemp -d "${TMPDIR:-/tmp}/free-agent.XXXXXX")"
trap 'rm -rf "$AGENT"' EXIT
for f in settings.json models-store.json; do [ -f "$HOME/.pi/agent/$f" ] && cp "$HOME/.pi/agent/$f" "$AGENT/"; done
python3 - "$HOME/.pi/agent/auth.json" "$AGENT/auth.json" <<'PY'
import json, sys
src = json.load(open(sys.argv[1]))
json.dump({k: v for k, v in src.items() if k == "openrouter"}, open(sys.argv[2], "w"))
PY
exec bwrap --unshare-all --share-net --die-with-parent --new-session \
  --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/sbin /sbin \
  --ro-bind /etc /etc --ro-bind /run/systemd/resolve /run/systemd/resolve \
  --dev /dev --proc /proc --tmpfs /tmp --tmpfs "$HOME" \
  --bind "$AGENT" "$HOME/.pi/agent" \
  --ro-bind "$HOME/.pi/agent/install" "$HOME/.pi/agent/install" --ro-bind "$HOME/.pi/agent/bin" "$HOME/.pi/agent/bin" \
  --symlink "$(readlink "$HOME/.local/bin/pi")" "$HOME/.local/bin/pi" \
  --ro-bind "$REPO" "$REPO" --bind "$OUT" "$OUT" \
  --setenv HOME "$HOME" --setenv PATH "$HOME/.local/bin:/usr/bin:/bin" "$@"
