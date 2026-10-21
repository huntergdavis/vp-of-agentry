# Dependency rule: boring, open, replaceable

Owner, 2026-10-21 (#1164): *"herdr is great, but I'm worried it's going to turn
into a corporate product eventually... I don't want to be dependent on that for
such a key functionality. We're just using unix tools and source code we can
derive now... standard unix tooling is a great basis for anything, boring
technology."*

This rule exists so that concern never has to be re-argued. It applies to every
component Dunking Sheep depends on for a **key function**.

## The rule

Every key capability must satisfy **both**:

1. **An open, documented interface.** Either a protocol we can read (JSON-RPC,
   HTTP, a documented CLI, a file format) or source we can derive from. A
   feature reachable only through one vendor's private UI does not qualify.
2. **A tested fallback on boring unix primitives.** Unix domain sockets, PTYs,
   `tmux`, `ps`/`/proc`, files, SQLite, `cron`/timers, exit codes. The fallback
   must be exercised by tests, not merely documented — an untested fallback
   rots silently and the dependency quietly becomes hard again.

If a capability can satisfy only condition 1, it may be **an adapter** but must
never be **the only path**. If it can satisfy neither, it does not go in a key
position.

## Where this already bites

- **Terminal backend.** `DUNKINGSHEEP_TERMINAL_BACKEND` selects herdr or tmux;
  the tmux path is real (isolated-server trial, 4 of 5 gates, close rail
  verified). Herdr is the *default*, not the only implementation.
- **The busy/idle signal** is the one function with no boring fallback yet, and
  therefore the one place herdr is genuinely load-bearing. It is being removed
  by using each tool's **own** protocol: codex `turn/started` / `turn/completed`
  over its local JSON-RPC socket, pi's extension events. Claude has no documented
  turn boundary yet; that gap is the last vendor-shaped hole and is under
  research.
- **Storage** is SQLite (embedded, a file), not a server. Same instinct: fewer
  daemons, no migration cliff, backup is `cp`.
- **Postgres is fine where it earns its keep** (concurrent multi-writer, real
  queries), but adding a server where a file would do is the opposite of boring.

## What "the VP tests the fallback" means in practice

When a key function gains a vendor adapter, the PR that adds it also adds or
extends the test that runs the boring fallback. A green adapter test with a dead
fallback is a finding, not a pass.

## A local protocol is not a local dependency

Learned 2026-10-21, codex steer. The app-server protocol is local (a unix
socket, a generated JSON schema, a documented method set) and looked like the
clean escape from terminal scraping. It is not usable without a **remote**
step: `remote-control pair` calls
`https://chatgpt.com/backend-api/wham/remote/control/server/enroll`, which
answers **403 `{"detail":"Multi-factor authentication required"}`** until the
account completes MFA. The socket is local; the authorization is not.

So the rule above gets a third question: **where does the authorization come
from?** An interface can be open and local and still be gated by a vendor's
server, and that gate is the dependency, not the socket. Ask for it explicitly
before counting a protocol as an escape hatch.

Consequence here: herdr remains required for codex as a **stable fact** with a
named reason (experimental surface, CLI 0.162.1 vs app-server 0.163.0, MFA-gated
enrollment), revisit only if the account completes MFA and the surface
stabilises.
