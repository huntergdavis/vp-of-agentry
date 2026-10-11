#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/uvicorn ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
if [[ ! -f web/dist/index.html ]]; then
  npm install --prefix web
  npm run build --prefix web
fi
exec .venv/bin/uvicorn server.app:app --host "${VP_BIND:-0.0.0.0}" --port "${VP_PORT:-8787}" --workers 1
