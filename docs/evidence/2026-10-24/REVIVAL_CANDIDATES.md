# Revival candidate evidence - decision aid, NOT a recommendation

## Live, NOT revival candidates

| lane | state |
|---|---|
| w9:pH (vp of agentry) | live as %1 (the VP writing this); 28 MB of pre-incident record preserved on purpose and deliberately not resumed - reviving it would replace the live operator |

Generated 2026-10-24 12:47 PDT. Source: launches.json, lanes.json, tasks.db, session files on disk (read-only).
CAREFUL: uncommitted/pushed counts are REPO-level facts about the workspace, not claims about what that lane did - a shared tree can carry another lane's work. Read them as 'state of the tree this lane lived in'.

Per VP i23197: no ranking, no recommendation. `owner loses` and `revive costs` are facts to weigh, not verdicts, and are blank where the record does not say.

## Groups the decision can actually be made on (max eight; the rest are listed below)

| what the work was | lanes in the group | what the owner loses if it stays dark |
|---|---|---|
| Poolrad - the PM lane and its parallel labs | wV:p2, wW:p1, wW:p2, wW:p3, wW:p4, wW:p5, wW:p7, wW:p8 | 224 MB of its own history across 8 lane(s); 7 message(s) waiting unread in its mailboxes; 3 open task(s): Play Poolrad QoL: programmatic DOSBox-X save states + quick ; Play Poolrad: fix cross-session DOSBox-X save-state load (se |
| Crackdown - native renderer work (multi-week owner mandate) | wS:p3, wS:p5, wW:p6 | 101 MB of its own history across 3 lane(s); 1 message(s) waiting unread in its mailboxes |
| Poolrad decomp - review lane (PRs awaiting an independent reviewer) | wR:p1 | 78 MB of its own history across 1 lane(s); 1 open task(s): Review PR #1526 (R2 validation) - no-self-merge requires an  |
| the phone lane (t52) | wY:p2 | 53 MB of its own history across 1 lane(s); 1 open task(s): Phone (SM_F766U): verify KartPad DATA count on device (2018  |
| Slamdemonium and the learnings miner | wH:pD | 32 MB of its own history across 1 lane(s); 1 message(s) waiting unread in its mailboxes |
| the nerve centre and your desk - delivery, registry, alarms, answers | w0:p1, w8:p8, w9:pS, wZ:p2 | 22 MB of its own history across 4 lane(s); 8 message(s) waiting unread in its mailboxes; 11 open task(s): DS1 Finish message state: replied + delivered definition; DS2 Git-merges section in project summary |
| the interface you look at - web view and dashboards | w9:pV, w9:pZ, wV:p3, wV:p4 | 16 MB of its own history across 4 lane(s); 3 message(s) waiting unread in its mailboxes; 18 open task(s): Always-visible (non-overlay) scrollbars inside the web app: ; Build the new interface per the design queue (owner mandate: |
| Poolrad decomp - free-model checker lane | wR:p3 | 14 MB of its own history across 1 lane(s); 1 message(s) waiting unread in its mailboxes; 1 open task(s): Collector SQL draft (t40 free-model): ops_snapshot.py querie |

## Verifiable from the lane's own record (appendix, one row per lane)

| pane | workspace | agent | prior purpose (from tasks) | session id | session size | last turn | messages waiting | last thing its own turn says | owner loses if not revived | revive costs |
|---|---|---|---|---|---|---|---|---|---|---|
| w0:p1 | /home/hunter/workspace/chief-of-staff | pi | not recorded in tasks.db | a16c5b-e337-71a8-b8a8-2be67b4d6bac.jsonl | 0.9 MB | 1.7h ago | 0 | Green light is away: dunkies is building pane creation + the lane→pane registry now, then restore wiring, then a rehearsal on two or three low-value lanes — nev | 0.9 MB of conversation it cannot reconstruct | one pane, one session resume |
| w8:p8 | /home/hunter/workspace/dunkingsheep | pi | MCP/CLI/API audit: dedupe and merge tool surface, keep context small; Memory service v1: implement schema, async ingest, | a14ae4-5c27-7224-ac08-9b7ded0021b7.jsonl | 20.0 MB | 1.2h ago | 0 | Green — **675 tests OK (1 skipped)** — and the last hour produced two findings worth more than the code. **1. The dispatcher timer was INACTIVE after the flip.* | 20.0 MB of conversation it cannot reconstruct | re-opens 11 task(s); one pane, one session resume |
| w9:pS | /home/hunter/workspace/chief-of-staff | pi | not recorded in tasks.db | a16c5b-e337-71a8-b8a8-2be67b4d6bac.jsonl | 0.9 MB | 1.7h ago | 8 | Green light is away: dunkies is building pane creation + the lane→pane registry now, then restore wiring, then a rehearsal on two or three low-value lanes — nev | 0.9 MB of conversation it cannot reconstruct | one pane, one session resume |
| w9:pV | /home/hunter/workspace/vp-webui-lane | claude | Build the new interface per the design queue (owner mandate: clean, usable, no herdr overhead); UI1 Build stamp in left- | 089cfcf1-9f02-4b42-b3fb-cba5acea367b | 7.6 MB | 1.8h ago | 1 | I've stood down and told w9:pS (message i23090) what is committed and pushed. Nothing tracked is uncommitted in either repo, and t48, t58, t59 and t63 are untou | 7.6 MB of conversation it cannot reconstruct | re-opens 11 task(s); one pane, one session resume |
| w9:pZ | /home/hunter/workspace/design-lane | claude | Design lane: write deliverable 2 - prioritised implementation task queue for w9:pV and w8:p8 (owner mandate: clean inter | 5dc6d93b-7c8f-4906-a02a-de55b0c87084 | 1.5 MB | 8.7h ago | 0 | ``` ***************************************************************** TASKS.MD APPROVED ***************************************************************** ``` w9 | 1.5 MB of conversation it cannot reconstruct | re-opens 1 task(s); one pane, one session resume |
| wH:pD | /home/hunter/workspace/slamdemonium | claude | not recorded in tasks.db | f341143d-cffd-4df7-b8ba-e6981a4ba419 | 32.0 MB | 162.1h ago | 1 | I read the inbox message and marked it handled. Nothing needs doing. It's an announcement from "dunky pi": Dunking Sheep now has a built-in task queue. Agents c | 32.0 MB of conversation it cannot reconstruct | one pane, one session resume |
| wR:p1 | /home/hunter/workspace/poolrad-decomp-claude-lane | claude | Review PR #1526 (R2 validation) - no-self-merge requires an independent reviewer | 281c8700-5acc-438b-b93d-c061e28437eb | 78.2 MB | 1.3h ago | 0 | PR #1548 is open against main with CI green: a raw-CPU model of OVL_0038_0400, the handler behind dispatcher slot 11. I've sent it to the PM (i23112). Identity  | 78.2 MB of conversation it cannot reconstruct | re-opens 1 task(s); one pane, one session resume |
| wR:p3 | /home/hunter/workspace/poolrad-decomp-opencode-ds41flash | pi | Collector SQL draft (t40 free-model): ops_snapshot.py queries — review by dunky pi | a14c56-d196-777f-aaeb-0eac03c2083d.jsonl | 14.2 MB | 11.1h ago | 1 | [2026-10-30 09:12:00 PDT] Replied to the CoS in five lines — Poolrad staffing tonight: **wR:p3 (me) running** on checker coverage (#1443 batch 6, #1455 CI clari | 14.2 MB of conversation it cannot reconstruct | re-opens 1 task(s); one pane, one session resume |
| wS:p3 | /home/hunter/workspace/crackdown-switch | claude | not recorded in tasks.db | 704b1247-4c9c-4967-9f11-86e8e33a1a92 | 52.1 MB | 24.0h ago | 1 | I've stopped pruning; the 1.8 GB of game logs are untouched. The VP's three asks are answered (i22261). 1. **Retention rule:** written into `discovery/device-lo | 52.1 MB of conversation it cannot reconstruct | one pane, one session resume |
| wS:p5 | /home/hunter/workspace/crackdown-switch | claude | not recorded in tasks.db | 6eb58ddc-07d6-4355-8bd7-3ae6f058144b | 15.6 MB | 0.2h ago | 0 | # Environment update - Primary working directory: /home/hunter/workspace/crackdown-switch/rexglue-crackdown-native (was /home/hunter/workspace/crackdown-switch/ | 15.6 MB of conversation it cannot reconstruct | one pane, one session resume |
| wV:p2 | /home/hunter/workspace/vp-of-agentry | pi | Play Poolrad QoL: programmatic DOSBox-X save states + quick load menu + cursor hide + auto code-word (no LLM in the loop | a15277-fbe6-749c-a053-5da9794bed29.jsonl | 3.0 MB | 120.4h ago | 1 | Acknowledged and standing by. - **Staged binary intact:** `~/.local/share/vp-of-agentry/dosbox-x-2026.10.01`, SHA-256 `a11d55f0…3ebfe967`, `--version` confirmed | 3.0 MB of conversation it cannot reconstruct | re-opens 3 task(s); one pane, one session resume |
| wV:p3 | /home/hunter/workspace/herdr-webui | pi | Webapp overhaul: adapt herdr-webui fork to our herdr 0.7.4 and integrate as the full active-worker/terminal UI (replace  | a15558-b7f3-7758-ab4d-0b53c0517dbc.jsonl | 3.1 MB | 117.1h ago | 1 | t22 verification is complete and reported. Desk change is `5292329`, live since 15:29:56 PDT (no game/dosbox running). **Assigned verification — all pass** 1. * | 3.1 MB of conversation it cannot reconstruct | re-opens 4 task(s); one pane, one session resume |
| wV:p4 | /home/hunter/workspace/vp-of-agentry | pi | Webapp overhaul 2: streamline Poolrad dashboard to % completion numbers only; make Operations dashboard deterministic/au | a15558-bafd-76e7-879e-125ae7f0f3f8.jsonl | 3.8 MB | 117.0h ago | 1 | **t22 is closed on the board and the VP verified the final commit.** Lane is clean and standing by. ## Final lane state - **Branch** `vp/t18-clean` @ `28c3fdc`  | 3.8 MB of conversation it cannot reconstruct | re-opens 4 task(s); one pane, one session resume |
| wW:p1 | /home/hunter/workspace/poolrad-par-a | claude | not recorded in tasks.db | 8e56ee32-a62c-4d0f-8909-e0bfe24fcd39 | 35.5 MB | 0.2h ago | 0 | [2026-10-24 10:57:20 PDT] I raised a false alarm that par-b's pane was gone, and I've retracted it. The Dunking Sheep daemon was being redeployed at 10:55 (upti | 35.5 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p2 | /home/hunter/workspace/poolrad-par-b | claude | not recorded in tasks.db | 6410ff5a-5905-4bba-a618-08daa2d8a8fe | 78.3 MB | 0.7h ago | 1 | [2026-10-24 12:06:50 PDT] Batch 15 is done and up as PR #1549. The four new raw models (7F_0130/0185, 25_19DB, 25_1815) all compared equal in V1 on R4. In route | 78.3 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p3 | /home/hunter/workspace/poolrad-par-c | claude | not recorded in tasks.db | 8be65445-04eb-42a6-8753-73e66e31119b | 48.0 MB | 1.5h ago | 2 | PR #1547 (wiring batch W1) is open on a main base, and I've reported it to par-a (i23107). CI is pending. My earlier send to `wW:p1` failed, because that pane i | 48.0 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p4 | /home/hunter/workspace/poolrad-par-d | claude | not recorded in tasks.db | 1b771738-1514-4a36-b084-066dfc707931 | 3.7 MB | 0.2h ago | 0 | [2026-10-22 19:06:00 PDT] I've stopped, with no new work and no further pushes. The handover is with par-d2 (wW:p7), but my reply to the VP appears to have been | 3.7 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p5 | /home/hunter/workspace/poolrad-par-e | claude | not recorded in tasks.db | 150a30e0-d803-4e9f-840d-61eefad17462 | 28.3 MB | 0.2h ago | 1 | The 063A grant script is ready and checked. Its dry run gives the expected body (967 B, hash `f23626a4…`), and the leftover `NATIVE` constant naming the install | 28.3 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p6 | /home/hunter | claude | not recorded in tasks.db | b2f28115-af0d-4e53-91f8-d7f31f86543f | 32.8 MB | 0.2h ago | 0 | The VP approved banking the two cheap wins as default-off flags and holding the rewrite for the owner. Here's where each stands (reported in inbox i20839). **Sh | 32.8 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p7 | /home/hunter/workspace/poolrad-par-d | claude | not recorded in tasks.db | 732ac2a2-d091-43ef-bb32-e7fef7f85a44 | 27.1 MB | 1.5h ago | 1 | [2026-10-24 20:58:30 PDT] RES_00BA_16EC is a real but modest keystone: landing it makes 7 handlers fully composable, not 42. I measured this read-only on main 6 | 27.1 MB of conversation it cannot reconstruct | one pane, one session resume |
| wW:p8 | /home/hunter/workspace/poolrad-par-a | claude | not recorded in tasks.db | a189dbd9-1ae7-405b-bc4a-e69a738b5b87 | 0.6 MB | 45.5h ago | 1 | [2026-10-22 15:19:45 PDT] I read the reviewer brief (i21379) and sent my verdicts back to w9:pH (i21380). There are **3 open PRs, and I would accept none of the | 0.6 MB of conversation it cannot reconstruct | one pane, one session resume |
| wX:p2 | /home/hunter/workspace/learnings-miner | claude | not recorded in tasks.db | c6bad1f7-2516-4f7c-9b4c-34ff83cdf44d | 1.4 MB | 19.7h ago | 0 | I've written all four deliverables in `wiki/`, each marked DRAFT at the top. The evidence base is thin, though. I scanned the whole inbox with keyword counts bu | 1.4 MB of conversation it cannot reconstruct | one pane, one session resume |
| wY:p2 | /home/hunter/workspace/skies-android | claude | Phone (SM_F766U): verify KartPad DATA count on device (2018 pushed vs 2043 expected) and re-push if short; then the six  | c8ea3679-e0cc-4d61-9dae-039d17c5fa8e | 53.3 MB | 10.8h ago | 0 | Understood on both points, and nothing to do tonight. The phone still isn't attached to monkeydluffy (`adb devices` is empty), so I'm waiting for it. - **Mario  | 53.3 MB of conversation it cannot reconstruct | re-opens 1 task(s); one pane, one session resume |
| wZ:p2 | /home/hunter/workspace/chief-of-staff | pi | not recorded in tasks.db | a16c49-bb27-71e5-adcc-f6f82b9ccdde.jsonl | 0.0 MB | 14.7h ago | 0 | Read BRIEF.md in full, and pulled the ground truths digest. **Confirmed as Chief of Agent Staff** — owner-facing only; I federate between the owner, the VP of A | 0.0 MB of conversation it cannot reconstruct | one pane, one session resume |

## Stranded queue, measured from the store

**37 queued messages in 22 mailboxes with no live reader** (measured 12:47:09 from inbox.db; live addresses excluded: the three π - lanes and panes %1/%2/%4 - %3 and %5 are shells since the 12:37 exit). Probes from my own runner may be inside this number if one leaked - the runner sweeps them and reports FAIL loudly if it cannot.

Attribution below is by mailbox NAME only. A mailbox that does not carry a lane's name is counted here and never guessed into a lane; the damage record is not a backlog, and nothing is swept or delivered.

| mailbox | messages waiting |
|---|---|
| w9:pS | 8 |
| %3 | 4 |
| PM (par-a) (wW:p1) | 3 |
| vp of agentry | 3 |
| PM (par-a) | 2 |
| Chief of Staff (w9:pS) | 1 |
| par-c | 1 |
| w9:pH | 1 |
| w9:pM | 1 |
| w9:pN | 1 |
| w9:pV | 1 |
| wH:pD | 1 |
| wR:p3 | 1 |
| wS:p3 | 1 |
| wV:p2 | 1 |
| wV:p3 | 1 |
| wV:p4 | 1 |
| wW:p2 | 1 |
| wW:p3 | 1 |
| wW:p5 | 1 |
| wW:p7 | 1 |
| wW:p8 | 1 |

## Tree state - REPO-LEVEL facts, not attributable to any lane

Listed separately on purpose: a shared tree can carry another lane's work, so these numbers say what the directory holds, never what a lane did. Cut from the per-lane columns for exactly that reason.

| repo (workspace) | uncommitted files | unpushed commits |
|---|---|---|
| /home/hunter/workspace/dunkingsheep | 2 | 107 |
| /home/hunter/workspace/herdr-webui | 0 | 0 |
| /home/hunter/workspace/poolrad-decomp-claude-lane | 0 | 0 |
| /home/hunter/workspace/slamdemonium | 0 | 1 |
| /home/hunter/workspace/vp-of-agentry | 4 | 0 |

## Unverifiable - kept out of the table on purpose

| pane | label | why not verifiable |
|---|---|---|
| w11:p1 |  | recorded session file is missing on disk; no readable last turn in the session file |
| w9:pJ |  | launch row has no session id; no readable last turn in the session file |
| w9:pM | nav-fixer2 | launch row has no session id; no readable last turn in the session file |
| w9:pN | dashboard | launch row has no session id; no readable last turn in the session file |
| w9:pX |  | launch row has no session id; no readable last turn in the session file |
| wR:p4 | codex poolrad | recorded session file is missing on disk; no readable last turn in the session file |
| wR:p5 | codex-poolrad2 | recorded session file is missing on disk; no readable last turn in the session file |
| wR:p6 | codex-poolrad3 | launch row has no session id; no readable last turn in the session file |
| wS:p4 | crackdown-codex2 | launch row has no session id; no readable last turn in the session file |
| wV:p5 |  | recorded session file is missing on disk; no readable last turn in the session file |
| %1 | π - vp-of-agentry | no launch row (never captured) |
| %2 | π - chief-of-staff | no launch row (never captured) |
| %4 | π - dunkingsheep | no launch row (never captured) |
| w1:p2 | Claude Proj | no launch row (never captured) |
| w8:pE | usage-research | no launch row (never captured) |
| w9:p5 | VP of Agentry | no launch row (never captured) |
| w9:p7 | Opencode DS4.1Flash | no launch row (never captured) |
| w9:p8 | VP of agentry | no launch row (never captured) |
| w9:p9 | free-re1 | no launch row (never captured) |
| w9:pA | free-re2 | no launch row (never captured) |
| w9:pB | free-re3 | no launch row (never captured) |
| w9:pC | free-re4 | no launch row (never captured) |
| w9:pD | free-re5 | no launch row (never captured) |
| w9:pE | free-re6 | no launch row (never captured) |
| w9:pF | free-re7 | no launch row (never captured) |
| w9:pG | free-re8 | no launch row (never captured) |
| wB:p2 | Codex hunterdavis.com | no launch row (never captured) |
| wN:p0 | poolrad-639-d-u6c | no launch row (never captured) |
| wN:p1 | PM for Poolrad-decomp | no launch row (never captured) |
| wN:p11 | poolrad-639-h-u33 | no launch row (never captured) |
| wN:p12 | poolrad-639-f-next | no launch row (never captured) |
| wN:p2 | poolrad-research-bot | no launch row (never captured) |
| wN:p5 | poolrad-codex | no launch row (never captured) |
| wN:p6 | poolrad-claude-2 | no launch row (never captured) |
| wN:p9 | poolrad-codex-2 | no launch row (never captured) |
| wN:pC | poolrad-codex-keyroute | no launch row (never captured) |
| wN:pD | poolrad-codex-divide | no launch row (never captured) |
| wN:pE | poolrad-fullc-review-a | no launch row (never captured) |
| wN:pF | poolrad-fullc-review-a | no launch row (never captured) |
| wN:pG | poolrad-fullc-u9b | no launch row (never captured) |
| wN:pH | poolrad-fullc-u68 | no launch row (never captured) |
| wN:pJ | poolrad-resident-runtime | no launch row (never captured) |
| wN:pK | poolrad-replay-join | no launch row (never captured) |
| wN:pM | poolrad-function-census | no launch row (never captured) |
| wN:pN | poolrad-replay-join | no launch row (never captured) |
| wN:pP | poolrad-function-census | no launch row (never captured) |
| wN:pR | poolrad-display-callee | no launch row (never captured) |
| wN:pS | poolrad-claude-3 | no launch row (never captured) |
| wN:pT | poolrad-function-ceiling | no launch row (never captured) |
| wN:pV | poolrad-claude-c1-replacement | no launch row (never captured) |
| wN:pW | poolrad-qa-capacity-replacement | no launch row (never captured) |
| wN:pX | poolrad-639-c-u5e | no launch row (never captured) |
| wN:pY | poolrad-639-g-u20 | no launch row (never captured) |
| wN:pZ | poolrad-639-w-u1c | no launch row (never captured) |
| wR:p2 | codex poolrad | no launch row (never captured) |
| wS:p1 | wS:p1 | no launch row (never captured) |
| wS:p2 | crackdown-codex | no launch row (never captured) |
