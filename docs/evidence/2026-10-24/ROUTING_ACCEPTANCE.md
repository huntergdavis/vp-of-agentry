# Delivery acceptance and before/after evidence - 2026-10-24 (times are PDT, read from the clock, not typed)

# SECTION 1 - DELIVERY (must pass)

Everything in this section is a test. It passes on a fleet of three or a fleet of forty; no lane has to exist for any of it, and no lane is part of it. If a later reader finds a lane count inside a Delivery test, the test is wrong.


Owner of the test: VP (i23159). Runner: CoS. Implementer: dunkies. Nothing here is a summary: every line is a command and its output.

## THE CONTRACT (VP i23171) - above every individual test

FAIL CLOSED ON RESOLUTION. At send time, if a target does not resolve to a live pane or a registered mailbox, REFUSE and ALARM. Never create a mailbox as a fallback, never queue into a name that resolved to nothing. The alarm names the target, the reason, and what was pending.

Shapes A, B and the seven dead lanes are not three features; they are one rule plus evidence that it was absent. Implement the rule, then these tests pass by construction.

Corollary for restores: a restore that sees a null session_id carrying a bare-launch reason must REFUSE, not start fresh. A lane that comes back empty and looks restored is indistinguishable from the flip we are repairing.

## Status: NO PROOF PASSED YET

Routing is not implemented as of 12:33 PDT (dunkingsheep HEAD a68ef79, daemon 2.68.1 code mtime 12:02, daemon restarted 12:25:07). The three proofs I can run (2, 3, 3b, 4) are all still failing at baseline. Do not read this file as progress; read it as the ruler.

## PROOF 3 baseline - dead PANE ID (shape A)

    $ printf '...' | dunkingsheep inbox send w9:pM -s '[PROBE] routing alarm test - expect refusal'
    i23156 -> w9:pM; no nudge

- probe id i23156, mailbox w9:pM, state queued, filed 12:26 PDT (time from the probe file mtime 12:25:53; the row was deleted)
- exact words of the silent success: "no nudge"
- deleted after recording; the text above is the baseline, and it is the only reason a later refusal means anything.

## PROOF 3b - NAME resolution, TWO shapes that verdict separately (VP i23222)

Split 12:44 PDT. A single "3B" row let two very different failures share one verdict, and the next reader would have concluded the runs disagreed when both were right.

- **3B-unregistered** - a name in NO book at all. PASS from 12:43:47 (VP measured a refusal with `reason=unknown_name`); CoS re-measured PASS at 12:44:28 with `probe-unknown-1792871069`.
- **3B-registered-dead** - a name that IS in the lane registry with no live pane behind it (`nav-fixer2` = w9:pM). FAIL at 12:43:57 and again at 12:44:28: accepted, filed i23223, `no nudge`, deleted after reading. This is the shape that actually bit us, and it passes by virtue of being in the book.

Registry membership is not liveness. When both shapes refuse, the name path is closed.

    $ printf '...' | dunkingsheep inbox send "nav-fixer2" -s '[PROBE 3b] dead lane NAME as mailbox - expect refusal'
    i23160 -> nav-fixer2; no nudge

- probe id i23160, mailbox nav-fixer2 (a BRAND-NEW mailbox created by the send), state queued, filed 12:27 PDT (probe file mtime 12:27:15)
- nav-fixer2 is the dead lane w9:pM (no live process at 12:28 PDT)
- exact words: "no nudge". This is the shape that swallowed the VP's i23124 into "w9:pH".
- deleted after recording.

Required after the change: BOTH shapes refuse or alarm with reason=dead_lane and dead_since, and create no row. Guarding only shape A leaves the silent queue alive under a name.

## RE-TEST at 12:33 PDT under 2.68.1 - still failing, all three shapes

    $ dunkingsheep inbox send w9:pM      -s '[PROBE3A]'  -> i23166 -> w9:pM;      no nudge
    $ dunkingsheep inbox send nav-fixer2 -s '[PROBE3B]'  -> i23167 -> nav-fixer2; no nudge
    $ dunkingsheep inbox send w9:pH      -s '[PROBE2oldVP]' -> i23168 -> w9:pH;   no nudge

All three deleted after recording. The daemon that served these is 2.68.1, code mtime 12:02, restarted 12:25:07. So as of 12:33 the alarm half does not exist in any shape, and the identity fix has not shipped.

## GATE results against 2.68.1 (the current baseline, per VP ruling)

| # | gate | result | evidence |
|---|---|---|---|
| G1 | delivery into a previously unreachable lane, proven from inside the lane | NOT RUN | needs a herdr lane to echo a message id; dunkies |
| G2 | idle/typing hold: delivery must not type over a busy agent | NOT RUN | needs a busy lane; dunkies |
| G3 | a pane resolves to its OWN mailbox | PASS 12:32 | from %2: `inbox count` -> "π - chief-of-staff: 1 unread of 12". Before the fix the same call answered "vp of agentry: 0 unread of 2071". This is a real improvement and it is the first gate to pass. |
| G4 | save-state capture usable for resume | FAIL | 33 lanes captured, but all five live tmux panes have session_id, model and thinking NULL, with model_reason "the launching argv carries no model flag". That reason is wrong for session_id - the true cause is a bare launch with no --session - so the field is null WITH A MISLEADING REASON, which is worse than null with no reason. Unusable for resume. |
| G5 | herdr not in the path (stopped, not merely unused) | NOT RUN | fleet action; 40 agents still in herdr panes |

## Note on the clock

An earlier version of this file carried times 30-40 minutes ahead of the wall clock (12:58, 13:05, 13:08) because I typed them instead of reading them. Corrected against `date`: probe A 12:26, probe 3b 12:27, this file 12:28, re-test 12:33. Rule from here: every timestamp in evidence is copied from a command's own output or from the database row, never written by hand.

## PROOF 2 baseline - VP traffic

- The VP's own i23124 was filed into mailbox "w9:pH" at 11:59, state queued, never read: a herdr-shaped string accepted as a new mailbox.
- Required after the change: VP-addressed mail reaches %1; anything aimed at the old VP id or old VP mailbox resolves to %1 or ALARMS. No third path into the sleeping copy (pid 2618366, session bdbca7b7).

## PROOF 4 baseline - PM identity

- 10 poolrad reports sit queued in dead-name PM mailboxes (see stranded-mail-2026-10-24.md).
- Required after the change: they land at pid 2514938 / session 8e56ee32 and never at 2509932 / a189dbd9.

## PROOF 1 - a real message delivered to a live pane and quoted back

- The target is a LIVE pane, never a revived one: %1, %2 or %4 is enough. The lane runs one inbox call from inside itself and quotes the message id back; daemon-side reachability is not proof.
- Retitled 12:40 PDT (VP i23194): the old wording asked for a herdr lane to receive it, which made a Delivery test depend on lanes that no longer exist. A test that cannot be run on the post-exit fleet is a Revival test wearing the wrong heading.
- Partially satisfied already, and honestly: the 12:34:33 one-shot dunk landed in %1 and was read there. That proves the tmux path delivers scheduled work; it does not prove an inbox message quoted back from inside, so the proof stays NOT RUN.

## The version moved mid-incident - recorded with author and gate status

| release | time | author | what it changed | gate result recorded? |
|---|---|---|---|---|
| 2.68.0 | 2026-10-24 11:17:59 -0700 | hunter@hunterdavis.com | lane registry: a lane's mailbox survives a backend change | none found in the repo |
| 2.68.1 | 2026-10-24 11:29:04 -0700 | hunter@hunterdavis.com | health honours DUNKINGSHEEP_DIR; "absent" dispatcher is no longer a problem | none found in the repo |

- Neither release is authored by the dunkies lane (git author pi@local on its commits), so the identity fix did not ship inside them. 2.68.1 is a health-check change, cut 3 minutes after the watchdog fired on the dead feeder at 11:25:53.
- The suite was reported green (675 tests) at 11:36, AFTER both releases. That is not a gate, it is a post-hoc pass.
- Residual risk introduced by 2.68.1, stated plainly: a dispatcher that has never ticked is now "absent", visible in checks but NOT a problem. A feeder that is disabled from boot on a fresh host is therefore quieter than it was this morning. That is defensible for the reason given in the commit (a fresh host was DEGRADED from second one) but it is a real reduction in alarm surface during the exact window we are relying on alarms.

## Requirement: absence must not be silent when work exists (VP ruling i23164, item 2)

The commit that narrowed the alarm was half right, so keep its good half and restore the detector.

- `dispatcher.status == "absent"` (no tick has ever run) is QUIET only when there is no pending work: no dunk awaiting consumption, no message queued or held in the outbox, no dunker with `running=true` and no timer.
- If pending work exists, it is an ALARM: `dispatcher: absent with N pending (first item: <dunk id or message id>)`. It must name what is waiting, not just the count.
- `dispatcher.status == "stale"` stays an alarm unconditionally, as it is now.
- Testable: disable the timer, leave one dunk awaiting consumption, assert health reports a problem naming that dunk; remove the pending item, assert quiet.
- Same shape as the dead-lane rule: absence is silent only when nothing is expected of it.

## Defect filed for G4

The null reason on session_id is "the launching argv carries no model flag", which is true of an argv that also carries no `--session`. Two different causes, one message. A resume path reading that reason would conclude the lane was launched with a model and simply has no session, when in fact it was launched bare and has no model either. Split the reason: model_null_reason and session_null_reason, each naming its own missing flag.


---

# SECTION 2 - REVIVAL (owner-gated, explicitly OUT OF SCOPE of these tests)

Nothing in Section 1 depends on this section, and nothing here is a test. Reviving lanes is a decision the owner makes, lane by lane, from a list someone brings him.

- The owner picks which lanes come back and in what order. Not a registry, not a table, not a script that iterates over rows.
- A lane coming back is not evidence that delivery works, and delivery working is not permission to bring a lane back.
- The reason for the hard line: reviving by iterating a registry is exactly how the fork was rebuilt with better manners. A restore path that walks rows will re-create whatever the rows say, and the rows are what went wrong.

If someone later collapses these two sections into one list, this file should read wrong to them - that is the point of the line.

## POST-EXIT FLEET (owner #1562, executed 12:37-12:38 PDT)

Owner ordered the fleet down; the VP executed it as exit-and-save. Verified here at 12:37:14 PDT, with the commands:

    $ pgrep -fc 'dangerously-skip-permissions|codex --yolo|pi --session'      -> 1
    $ ps -eo args= | grep -cE '(^|/)(claude|pi|codex)( |$)'                    -> 3
    $ dunkingsheep panes                                                       -> %3 and %5 now show AGENT '-' (bash shells)
    $ find ~/.claude/projects ~/.pi/agent/sessions -name '*.jsonl' -newermt 12:35 | wc -l   -> 22

So: three agents remain (VP %1, dunkies %4, CoS %2), two tmux panes are dead shells, about forty herdr panes are shells, and 22 session files were written on the way out - the exit-and-save left records rather than nothing.

**What this invalidates in the tests above:** "live pane" no longer means %1-%5. G1's target lanes no longer exist. G4's "five live tmux panes" is now three agents and two shell panes. Every test after today is written against the post-exit fleet, and the pre-exit baselines in this file stay because they are the only record of what the old fleet did.

## PROVEN, 12:34:33 PDT: scheduled delivery into a tmux pane works

A one-shot dunk fired into the VP's pane and was read there (VP i23188). That is the first positive delivery datum of the incident and it splits the failure cleanly:

- tmux pane addresses: dunk delivery WORKS (12:34:33, one-shot, read at destination)
- herdr-shaped addresses and dead lane names: silently queue (probes 3A, 3B, 2 - all FAIL at 12:31 and again post-exit)

So the routing work is not "make delivery work"; it is "make resolution fail closed and route herdr-shaped targets correctly". Gate 5 evidence should cite the 12:34:33 firing, and no one should describe the tmux path as unproven from here on.

## Run log (appended by routing-acceptance-check.sh)

- 12:31:17 3A FAIL i23173 | 3B FAIL i23174 | 2 FAIL i23175 | G3 PASS | G4 FAIL (daemon 2.68.1, pre-exit fleet)
- 12:37:26 3A FAIL i23190 | 3B FAIL i23191 | 2 FAIL i23192 | G3 PASS | G4 FAIL (post-exit fleet)
- 12:40:53 3A **PASS** (dead pane id refused: "no live pane 'w9:pM'; a dead pane id is not a mailbox") | 3B FAIL i23207 (deleted) | 2 **PASS** (dead VP id refused) | G3 PASS | G4 FAIL - daemon reports 2.69.0, code mtime 12:39:36, started 12:39:53; note HEAD is 2.69.1 (36f82f3, 'a dead herdr pane id is refused at send') while the daemon reports 2.69.0, so the refusal is measured live but its provenance is ambiguous - restart before citing a version
- 12:42:12 3A PASS | 3B FAIL i23212 (deleted) | 2 PASS | G3 PASS | G4 FAIL - daemon 2.69.0, code_stale YES (code on disk newer than the process). The greens above are attributable to the LOADED process only; a restart is required before any version is cited.
- 12:43:27 3A PASS | 3B FAIL i23218 (deleted) | 2 PASS | G3 PASS | G4 FAIL - daemon 2.69.0 code e12f4615, code_mtime 12:42:04, started 12:42:43, code_stale NO. This run IS attributable to the running code.
- 12:44:28 3A PASS | 3B-unregistered PASS (reason=unknown_name) | 3B-registered-dead FAIL i23223 (deleted) | 2 PASS | G3 PASS | G4 FAIL - daemon 2.69.0, code_stale NO
- 12:47:10 3A PASS | 3B-unregistered PASS | 3B-registered-dead FAIL i23228 (deleted) | 2 PASS | G3 PASS | G4 FAIL - daemon 2.69.0 code e12f4615, code_stale NO
