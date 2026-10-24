# Incident 2026-10-24: the tmux pane flip

Written after the delivery gate closed, not around it. Every measurement referenced here
lives in `docs/evidence/2026-10-24/ROUTING_ACCEPTANCE.md`, cited by section rather than
copied, so the two cannot drift. The revival input is
`docs/evidence/2026-10-24/REVIVAL_CANDIDATES.md`.

## 1. Timeline (America/Los_Angeles)

| time | what happened | evidence |
|---|---|---|
| ~11:00 | Daemon restarted on the tmux backend ("the flip"). Five tmux panes were started with a bare command - `pi`, `claude --dangerously-skip-permissions` - never `pi --session <recorded>` | acceptance file, "POST-EXIT FLEET" section and the audit it cites |
| 11:04-11:07 | Five tmux twins created (cos %2, dunkies %4, vp %1, par-a %3, ports %5). The herdr incarnations kept running: five lanes existed twice | acceptance file, fork table |
| 11:09-11:36 | Mail and dunks resolved on the tmux backend, so the herdr incarnations went deaf while still acting. Scheduled work: 0 of 4 dunks could fire (targets were herdr ids; no dunker had a timer) | evidence file + `docs/HERDR_REMOVAL_AUDIT.md` |
| 12:25-12:27 | First acceptance probes: a dead pane id, a dead lane name and the old VP address were all accepted and queued silently (i23156, i23160) | "PROOF 3 baseline" |
| 12:33 | Re-test on 2.68.1: the same three shapes still queued silently (i23166-i23168) | "RE-TEST at 12:33" |
| 12:37-12:38 | Owner ordered the fleet exited (#1562). 42 agent processes exited, 8 with the hard signal, zero stragglers. Two tmux panes (%3, %5) became shells; ~40 herdr panes became shells | "POST-EXIT FLEET", measured independently at 12:37:14 |
| 12:40:53 | First greens: dead pane id and the old VP address refused (2.69.0) | run log |
| 12:41-12:53 | Registered-but-dead name still queued. Three independent measurements from two agents (12:52:50, 12:53:00, 12:53:51) | run log |
| 13:03-13:06 | 2.69.3 refused the third shape, but with a third token (`unhoused_lane`) and no `dead_since`. Behaviour green, vocabulary still being corrected | run log, 13:04:39 |
| 13:11:12 | 2.69.4 restarted: one token, `dead_lane` | run log |
| 13:12:21 | All routing shapes green on committed code: daemon code hash `eeefc6eb46ed` equals `sha256(dunk_core.py)` on disk, HEAD `17760dd`, clean tree, `code_stale no` - two tokens at this point | run log |
| 13:13-13:14 | 2.69.5 (`d6b995e`) restarted: three tokens, because there are three states. Re-verified from %1 by the VP: `unhoused_lane`, `unknown_name`, dead pane id refusal, zero rows created | run log 13:14:56; verified independently by the VP |

Wall-clock discipline: the acceptance file records `code_mtime`, `started_at` and
`code_stale` on every run because an earlier version of it carried hand-typed times that
were 30-40 minutes ahead of the clock. That error is recorded in the file rather than
quietly fixed.

## 2. What was actually broken - four defects, not one story

Numbers rule for this document: **no figure appears here that is not in
`docs/evidence/2026-10-24/ROUTING_ACCEPTANCE.md`, and nothing is copied from it - only cited.**
Whoever edits this next keeps that rule. The evidence file is the measurement; this document
is the account.

**Delivery.** Resolution at send time used two wrong rules. A herdr-shaped string that
matched nothing was accepted as a brand-new mailbox name and queued forever ("successfully
sent", never read); and a name that was in the lane registry was treated as alive, so a
lane with no pane behind it swallowed mail silently. Both were invisible: senders saw
success, and nothing counted the queue.

**Identity.** `inbox count` in pane %2 answered `vp of agentry` rather than the lane's own
mailbox, and a message addressed to the VP's old address filed itself into a mailbox named
`w9:pH`. Separately, `launches.json` attached the two VP claude session ids to dead lane
rows, so "resume from launches.json" on a dead id would have forked the VP voice into the
owner channel.

**Authorisation.** This is its own defect and the most dangerous thing found today. A new
tmux lane inherited a dead herdr pane id from its environment and was therefore
**authorised as the VP** while believing it was itself: identity and authorisation were
riding the same stale variable. The reusable lesson is the fix, not the symptom - **the
terminal you are in wins over an inherited claim.** Any lane, daemon or tool that accepts an
identity from the environment must check it against the terminal it is actually running in,
and refuse when they disagree, rather than trusting the inherited value because it is
present.

**Capture.** Save-state rows carried `session_id`, `model` and `thinking` as null for every
live tmux pane, with a single reason string ("the launching argv carries no model flag")
that belongs to `model` and is false for `session_id`. A restore therefore had nothing to
refuse on, which is exactly how a bare twin can look like a resumed lane.

## 3. What was decided, and why

- **History wins, but operators are not killed to get it.** The recorded session is the
  survivor; the duplicate is exited only after its own session file is verified non-empty
  with an advancing mtime. The lane holding an incident keeps its operator: resuming the
  VP's pre-incident 27.9 MB record would have replaced the only voice in the owner channel,
  so that record was preserved and left un-resumed, deliberately.
- **Identity is the session**, never the cwd and never a process count. Two independent
  agents in one tree are two agents; neither is killed to make a table tidy, and neither is
  merged.
- **Registered is not live.** A registry row proves a lane once existed. Liveness must come
  from a recorded live pane; absent that, the lane is dead.
- **Fail closed on resolution.** At send time, a target that does not resolve to a live pane
  or a registered lane is refused with a reason, and refusal never creates a mailbox.
  Reads stay permissive: stranded mail must remain readable and archivable.
- **No static dead-lane list in the resolver.** Deadness is a verdict reached at send time,
  never a file read from disk. The inventory measured during the incident is a frozen
  archive with its measurement window, and its only reader is a future revival decision.
- **Delivery acceptance is separate from owner-gated revival.** The delivery tests pass on
  a fleet of three or forty; nothing comes back because a table says so.
- **The VP lane is not resumed, and that is a decision, not an omission.** Its 28 MB of
  pre-incident record is preserved untouched; the live session acts. Resuming the record
  would replace the operator who is holding the incident, the owner channel and every ruling
  made during it. A later reader will see a candidate row and an unrevived lane and must know
  the two facts are the same decision.
- **Three refusal tokens, after a reversal.** `unknown_name` (never a lane) and `dead_lane` (a lane
  with no live reader). The operator has two actions, fix the typo or restore the lane; a
  third token describing which backend a lane was never housed on encoded an implementation
  detail, not a situation - but the final answer is three, and the churn is recorded rather
  than tidied. Two tokens were ruled; `edb6dae` (2.69.3) shipped `unhoused_lane`; the VP
  reversed to three states at 13:06; `17760dd` (2.69.4) committed two again; the reversal was
  then withdrawn and `d6b995e` (2.69.5) committed three, which is what is verified now:
  `unknown_name` (never a lane), `dead_lane` (marked dead with `dead_since`), `unhoused_lane`
  (exists, not marked dead, no live pane on this backend, no invented date). The word flipped
  twice in ten minutes and the reversal was the VP's, not the lane's. Kept because the
  acceptance run at 13:04:39 shows behaviour green with the wrong vocabulary, which is why
  vocabulary is tested separately from behaviour.

- **`dead_lane` has no producer yet, and that is a procedure rather than a gap.** Nothing is
  marked dead today: the refusal for a lane with no live pane is `unhoused_lane`, which means
  "not running here". When the owner declines a lane group at revival, those registry rows
  get `alive=false` with `dead_since=<date>`, and from then on mail to them says dead since a
  date rather than merely not running. The owner's revival decision is therefore what feeds
  the registry - parked and gone are different states, and only a decision makes a lane gone.

## 4. Revival runbook - one lane, start to finish

1. **Pick the lane.** From `REVIVAL_CANDIDATES.md`, by the owner's decision. The aid groups
   lanes by what the work was and lists the per-lane record; it contains no recommendation.
2. **Refuse ambiguity.** A lane with more than one candidate launch row is refused, not
   guessed. An empty session field is no candidate. Never key a resume off the cwd (the pi
   sessions dir for a workspace can hold another lane's session) and never off a file mtime.
3. **Refuse claimed sessions.** A session id already claimed by a live pane is refused and
   alarmed, never silently skipped. Never resume the two quarantined VP sessions
   (`e894e1d4`, `bdbca7b7`).
4. **Resume by session id, no bare launches.** `pi --session <id>` or
   `claude --resume <id>`, with the recorded model, thinking level and cwd. A twin started
   without `--session` is the defect this incident began with.
5. **Prove it from inside.** The lane itself runs one inbox call and one task call and
   quotes the ids back. Daemon-side reachability is not proof: a restored lane can come back
   without MCP - no inbox, no tasks, no memory - and look healthy.
6. **Record it.** Lane, session id, tmux window, resumed y/n, evidence, and - if the lane had
   an old incarnation - how long the two overlapped.

## 5. What is still open

- **G4, capture - RED, deliberately left red in this document.** Every live pane still
  records a null `session_id` with a reason that belongs to another field. A restore has nothing to refuse on until this is fixed; the
  requirement is a per-field reason and a restore that refuses a null session.
- **The aligned alarm.** An absent dispatcher is quiet since 2.68.1. The agreed rule -
  absent with nothing pending is quiet, absent with pending work alarms and names the
  pending item - is written into the acceptance file and not yet implemented.
- **Stranded mail.** 37 queued messages in 22 mailboxes with no live reader, deliberately
  untouched: they are the damage record and an input to the revival decision. Nothing in
  this incident swept or re-delivered them.
- **The parked per-pane herdr delivery sketch.** Cut on purpose: the fleet is exited and
  revival goes into tmux, so herdr-shaped delivery has no live reader to serve. It is kept
  as rollback notes only; re-opening it would be building for a backend we are leaving.
- **The gates are NOT all green, and this paragraph decides whether the release counts as
  gated.** Measured on 2.69.5: **G1 PASS** (a message delivered into a live lane and quoted
  back from inside it), **G3 PASS** (a pane resolves to its own mailbox), **G4 FAIL** (capture
  still null), **G2 NOT RUN** (idle/typing hold - needs a deliberately busy lane), **G5 NOT
  RUN** (herdr is still installed and running; it holds shells rather than agents now). So t50
  cannot cite a fully gated build: two gates pass, one fails, two have never been run.
- **The ungated owner releases (2.68.0, 2.68.1).** No gate results exist for either, and the
  run above does not retroactively gate them - it measures the current build, which is the
  only build anyone can cite.

## 6. A process hazard found while making this PR

The first version of this branch was cut from **local** `main`, which was carrying enough
unpushed commits that the pull request for a two-file incident report listed 66 files and
began with brief-style and handoff notes that had nothing to do with the incident. Nothing
was wrong with the content; the branch was simply built on a base that did not exist on the
remote.

Rule that follows, and it belongs to anyone making an incident or evidence PR: **cut the
branch from `origin/main`, not from local `main`, and check the file list before asking for
review.** A PR is reviewed by its diff, so a diff with unrelated work in it looks reviewed
without being reviewed - which is the same failure shape as a production change made without
running the detector. The rebuilt branch here has five commits and three files, which is what
was agreed.
