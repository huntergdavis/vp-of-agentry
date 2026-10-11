# VP of Agentry

An owner-only LAN desk for existing Herdr agents. It sends to the running VP and project PM panes through Dunking Sheep's guarded `send_text` command. It does not start a new model session.

## Start

```bash
./run.sh
```

Open `http://<this-host-on-your-LAN>:8787`. On first start, a random password and local API token are generated in `data/owner-credentials` (mode `0600`). The entire `data/` directory is ignored by Git. Sign in with the password, then remove that credentials file after storing the secrets in your password manager if desired. The API token remains in `data/auth.json` for local agents and `vpctl`.

Set `VP_BIND` and `VP_PORT` to change the listener. The default binds to all interfaces so your LAN devices can reach it. Limit access to your trusted LAN or a VPN; HTTP on a LAN does not encrypt traffic. The web UI requires authentication, sessions use HttpOnly SameSite cookies, login attempts are rate limited, and cross-origin browser requests are rejected.

To keep it running after an agent or terminal closes, run `./install-service.sh`. Check it with `systemctl --user status vp-of-agentry.service` and `./vpctl status`. The service restarts on failure and starts with your user session.

Requires Python 3.10+, Node 20+, Herdr, and a running Dunking Sheep daemon or a sibling `dunkingsheep` checkout. Set `DUNKING_SHEEP_DIR` if it is elsewhere. On first run, `run.sh` installs Python and Node dependencies and builds the frontend. Runtime data and uploads remain under `data/`.

## How it works

- **Chat:** messages are sent to the current Herdr pane for each channel using Dunking Sheep's guarded queue. The UI shows `queued`, `sent`, or `failed`; a sent state means submitted to the pane, not that the agent has answered.
- **Briefs:** an agent publishes a concise Markdown response with `echo 'Done' | ./vpctl brief --channel vp`. Agent briefs and owner messages are stored in SQLite, with paginated back-scrolling and paged search that opens the exact matching message.
- **Files:** images and other files up to 25 MB are stored locally under ignored `data/uploads/` and their absolute paths are included in the guarded message to the agent. The browser can download them only after signing in.
- **Live view:** the right panel shows recent terminal output from `read_pane`; it is a volatile view and is not presented as complete history. Durable agent responses require `vpctl brief` or the authenticated `/api/brief` endpoint.
- **API:** the owner can use the same API with the generated Bearer token, and `vpctl` is the command-line wrapper. The browser never accesses the Herdr or Dunking Sheep Unix sockets.

The channel selectors match current Herdr tab labels (VP of Agentry, Poolrad PM, website, Slamdemonium, Dunkies, and MonkeyDLuffy). Update `CHANNELS` in `server/app.py` if tab labels change. The remote MonkeyDLuffy tab is monitoring only unless an agent is present there.

## Reused software

The chat surface uses [ChatScope Chat UI Kit React](https://github.com/chatscope/chat-ui-kit-react) and [ChatScope styles](https://github.com/chatscope/chat-ui-kit-styles), both MIT licensed. Rich text uses [Tiptap](https://github.com/ueberdosis/tiptap) (MIT); Markdown conversion and display use [Turndown](https://github.com/mixmark-io/turndown) and [react-markdown](https://github.com/remarkjs/react-markdown), both MIT. This keeps the custom frontend limited to the project dashboard and bridge.

[Open WebUI](https://github.com/open-webui/open-webui) and [LibreChat](https://github.com/LibreChat-AI/LibreChat) were evaluated. Both offer mature self-hosted chat, uploads, and history. Their provider integrations expect model conversations and do not directly provide a durable, structured reply stream from an already-running Herdr pane. Integrating raw local file custody and the guarded send queue would require an adapter; this small bridge keeps those semantics explicit.

## Limits

Herdr `read_pane` exposes recent terminal text, not a structured full conversation. The desk persists what is sent through it and briefs posted back through the API, but cannot retroactively import every prior agent turn. Search covers this stored history. This is a single-owner LAN app; deploy behind HTTPS or a VPN for access over untrusted networks.
