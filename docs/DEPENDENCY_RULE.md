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

## Before you model a number, check the recorder

Three defects in one night, all the same shape: the instrument was throwing the
data away, and the model built on top of it was asked to explain noise.

1. `host_watch.append_sample` kept `history[-2:]` — enough for a *level*, useless
   for a *fit*. A band calibration was requested against a history that did not exist.
2. `pane_samples` recorded only the poolrad lanes, so "busy lanes" read 1 while 27
   panes were live. A fit would have produced "load per busy lane ~12".
3. A case-sensitive grep for `poolrad` returned zero, and "absent" was reported —
   the string was there with a capital P.

The rule: **when a decision depends on a number, prove the recorder first** — how
many samples, over what window, with which fields present. Say the sample count and
the window in the same sentence as the conclusion, or the conclusion is unfalsifiable.

## A flaky test is a defect until proven otherwise

2026-10-22: a close-path test failed intermittently on a loaded machine and never
in isolation. The cause was not the test. A stopped dunk's own countdown thread
wrote one more `Next: 60:00` outside the lock and without checking whether it was
still running, so a dunk that had just been closed reported itself as scheduled
again. Order determined the answer, which is exactly why it only appeared under
load.

Rule: when a test is flaky, the first hypothesis is that the product has a race,
and the reproduction to hunt is the *ordering*, not the timing. "It's the test"
is a conclusion that needs its own evidence.

## An executed script is immutable

2026-10-22: a deploy script was edited 14 seconds after a deploy started. Bash reads a
script *while executing it*, so it resumed at the old file's byte offset - which in the
new file fell mid-line. A spliced fragment ran on the wrong host and the script stopped.

Rule: **write a new file and rename it over the old one; never edit in place while
anything might be running it.** Same reason as the atomic snapshot write - a reader
must never see a half-written thing. On a shared device, record the script's sha256 in
the prerun checklist and have the deploy refuse if it changed between check and run.

## A lane is reachable or it is not - and presence is not reachability

2026-10-22, three variants of the same failure, each of which made a live pane
unreachable while every surface said it was present:

1. **Dead session.** The agent's connection died; the pane still rendered a
   composer. Four sends were typed and never submitted, and `skip_if_unconsumed`
   read that as "the lane is idle" for ten hours.
2. **Unsubmitted draft.** A nudge landed in the box and never submitted. Every
   later send was then held ('someone is typing') because the guard correctly
   refuses to type over a non-empty box - so one failed send locked the lane for
   ever.
3. **Placeholder read as a draft.** A harness prompt line such as
   `new task? /clear to save 497.4k tokens` is placeholder text, but the box
   reader treated it as somebody's unfinished message: the lane was permanently
   "typing" and could never receive anything.

Rules:
- Before asserting a lane is busy or idle, ask the only question that matters:
  **can this pane accept a message right now?** That is a checkable state
  (ready / blocked-with-reason / dead), not an inference from a process existing.
- A guard that refuses valid writes is worse than no guard: it converts into false
  alerts (the watchdog paged about four "unread" messages that could not be acked
  because the ack compared a decorated mailbox name literally).
- And the corollary for feeding work: **a lane that finishes and stops is a
  scheduling defect, not a lane defect.** Feeding must be deterministic (a queue
  and a timer), never dependent on a model being awake to notice.

## A check that proves spelling is not a check that proves function

The same defect appeared in two trees on the same night:

- `check_checker_builds.py --compile-only` compiled and bound a checker without
  ever executing its hooks, so an undefined register constant reached `main` and
  stayed there until a lane ran that audit by hand.
- `tests/test_inbox` asserted "every command is reachable from the CLI" by
  *grepping the help text*. It proved a name was spelled. When a smoke test finally
  executed all 86 commands, two of them (`clear_box`, `delivery`) were schema lies -
  and both were commands the night's operation depended on.

Rule: **grep, import, compile and list all prove that a NAME exists.** None proves a
handler runs. The test must execute the thing and assert a result - and for a command
with no required parameters, "returns a result" must mean a result, not a polite empty
success.

## A rule tested only in its happy path may be impossible in its only case

The context store's `supersede()` derived the same slug as the entry it replaced, so
on the same day, with the same subject, the new file collided with the old and the
command refused with "entry already exists". Supersession is the **only** mechanism by
which a ground truth may change - and the case it exists for (same day, same subject)
was the one case it could never serve. It was documented, and tested on a neighbouring
case.

Rule: for any mechanism that exists for **one** purpose - supersede, retire, rollback,
migration, restore, resume - the test must exercise **the case it exists for**, not a
convenient neighbour. A happy-path test on a mechanism with a single purpose proves
almost nothing.
