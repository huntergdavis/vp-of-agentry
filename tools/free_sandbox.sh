#!/usr/bin/env bash
# Run an UNTRUSTED free-model process with the whole filesystem read-only except one output dir.
#   tools/free_sandbox.sh OUTDIR command [args...]
# The prompt says 'read-only'; this is what enforces it for any tool the model calls (bash, edit,
# write). pi needs to write lock/session files under ~/.pi/agent, so it gets a throwaway COPY of
# that directory's small config files (sessions and extensions are not copied). Residual risk,
# stated plainly: the provider key is inside that copy and readable by the model - use a dedicated
# low-value provider key for free runs.
set -euo pipefail
OUT="${1:?output dir}"; shift
mkdir -p "$OUT"
AGENT="$(mktemp -d "${TMPDIR:-/tmp}/free-agent.XXXXXX")"
trap 'rm -rf "$AGENT"' EXIT
for f in "$HOME"/.pi/agent/*.json; do [ -f "$f" ] && cp "$f" "$AGENT/"; done
bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp \
  --bind "$OUT" "$OUT" --bind "$AGENT" "$HOME/.pi/agent" --ro-bind "$HOME/.pi/agent/bin" "$HOME/.pi/agent/bin" --ro-bind "$HOME/.pi/agent/install" "$HOME/.pi/agent/install" \
  --unshare-pid --die-with-parent "$@"
