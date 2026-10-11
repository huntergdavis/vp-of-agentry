# VP of Agentry

A private LAN desk for the owner's existing Herdr agents. Messages use Dunking Sheep's durable inbox where the agent has a unique mailbox; generic shared mailboxes use guarded exact-pane delivery. The website does not start a new model session.

## Run

```bash
./run.sh                    # first run installs dependencies and builds the UI
./install-service.sh        # optional: keep it running with systemd
./vpctl status              # health check
```

Open `http://<LAN-host>:8787`. The initial password and API token are in ignored `data/owner-credentials` (mode `0600`). Change the password with the gear icon, or edit that file's `Password:` line; the next sign-in applies a newer file. The API token is preserved. Set `VP_BIND`, `VP_PORT`, or `DUNKING_SHEEP_DIR` if needed. Access this HTTP app only on a trusted LAN or VPN.

## Delivery

Enter sends; Shift+Enter adds a line. Messages and uploads (up to 25 MB each) are saved in ignored `data/` and copied into a unique agent inbox when available. The chat shows **in inbox**, **read**, and **handled** as the agent processes them; state is checked every five seconds. Shared generic mailboxes use the guarded pane queue, and show **queued** or **sent**. A timeout is marked **delivery uncertain** and never resent automatically.

Agents post durable Markdown replies with `echo 'Brief' | ./vpctl brief --channel vp`. The right panel shows recent, volatile `read_pane` output; search covers stored website messages and posted briefs. The owner Bearer token works with the same API. A browser tab opened before an upgrade needs one refresh; newer tabs show an update notice.

The UI reuses MIT licensed [ChatScope](https://github.com/chatscope/chat-ui-kit-react), [Tiptap](https://github.com/ueberdosis/tiptap), [Turndown](https://github.com/mixmark-io/turndown), and [react-markdown](https://github.com/remarkjs/react-markdown). Open WebUI and LibreChat were evaluated, but their model-provider paths need an adapter to target a running Herdr pane and local guarded queue.

Checks: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`; authenticated browser check: `VP_TEST_SEND=1 .venv/bin/python tests/browser_smoke.py` (requires Playwright).
