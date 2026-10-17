# Operations metrics sources

The VP operations database is data/operations.sqlite3, which Git ignores. The file is mode 0600. The authenticated API is GET /api/ops-metrics; the local CLI is ./opsctl summary. Every record retains an observation time and source or evidence reference. A source outage is unavailable, never zero.

| Measure | Source and cadence | What it means | Limit |
| --- | --- | --- | --- |
| Pane staffing | Dunking Sheep panes, sampled each minute | Process presence by locally assigned role and reported state | Working, blocked, and done are terminal states, not verified productive work. |
| Recent PR state | Read-only GitHub PR list, at most every five minutes | Visible recent review and merge events | The last 100 PRs are a queue sample, not a whole-game completion denominator. Local unpublished work is absent. |
| VP message volume | Local VP messages SQLite, sampled each minute | Counts by channel and author role | Does not cover other conversations and stores no message text in the operations database. |
| Dunking Sheep flow | Aggregate metrics API, one-hour window at most every five minutes after daemon rollout | Message queue and handling counts with interval timestamps | Currently unavailable until the running daemon supports schema version 1. No message bodies, subjects, filenames, or account emails are accepted. |
| Weekly quota | VP direct /status observation, manually entered with provider, pane, time, reset, and evidence | Separate Codex and Claude percentages for the observed account | Stale readings retain their percentage and age. An unobserved provider shows no reading. Panes sharing an account must be grouped by reset cohort. Burn is calculated only within one provider, cohort, and reset after two direct readings at least 30 minutes apart. |
| Local progress | PM-reviewed goal observations with evidence reference | Credited strict full-C functions and measured local queues | Provisional parity gates and queue starts do not add strict full-C credit. |
| Published function coverage | Both accounting JSON files pinned to one GitHub main commit, sampled at most every five minutes | Strict full-C and verified identity counts divided by the PM-reviewed function ceiling | Percentages are minimum function coverage, not whole-game completion. Both files must describe the same original binaries. |
| Overall progress | PM-reviewed goal observations with evidence reference | Playable C demo gate and verified whole-game denominator | The playable demo is blocked until a same-state DOS/C frame; no verified whole-game denominator exists. |
| Fixed subscriptions | Owner-reported amounts entered privately with ./opsctl subscription | Latest monthly amount by provider and their sum | Excludes unknown taxes, add-ons, and usage charges; no amount is hardcoded in tracked source. |
| OpenCode model cost | Read-only aggregate of local OpenCode session costs in ~/.local/share/opencode/opencode.db, read on each summary request | All-time and Los Angeles calendar-month estimates matching the source used by `opencode stats` | Covers all local OpenCode projects. This is a model-cost estimate, not confirmed billed overage; do not add it to the $10 Go subscription. Missing or unreadable data is unavailable. |
| Host health | Latest private `host_watch.py` timer sample, read on each summary request | `/tmp` use/free space/inodes, load, CPU pressure, process and zombie counts, threshold state, and observation age | A sample older than three minutes is marked stale. Counts do not identify which process or file is abandoned; inspect before cleanup. |
| Fixed price per calendar hour | Latest owner-reported monthly fixed subscription sum divided by calendar hours in the current month | Subscription allocation per elapsed calendar hour | Not metered usage cost or cost per productive coder hour. |
| Function coverage speed | Change in published PM-reviewed strict full-C count divided by actual hours between comparable snapshots, at least one hour and at most 24 hours apart; percentage points also divide by the same reviewed bound | Reviewed function progress per hour | Unavailable until two comparable observations exist. PR merges, starts and provisional parity add no credit. |
| Model trials | Manually recorded pane, model, reasoning effort, hypothesis, dated start/end, and evidence | Distinct authored function outputs per trial; latest exact-head accepted bodies per completed trial hour by model and effort | Later repairs retain the original trial's authored output but do not inherit its acceptance. Trial hours exclude later PM review; tokens and metered dollars remain unknown unless separately sourced. A provisional authored body adds no accepted credit. |
| C body events | Exact local or published source head and evidence, with named reviewer for acceptance | Latest status per original function by event occurrence time, then insertion ID for ties | A late historical import cannot reverse a newer acceptance. This local trial ledger does not replace PM-reviewed published strict-C accounting. |
| Usage money and tokens | No billing source connected | Unknown | Pane activity and quota percentage cannot be converted to token or marginal dollar cost. |

The collector timer runs once per minute. GitHub and Dunking Sheep polling are throttled to five minutes. Roles are private local assignments entered with ./opsctl lane; the checked-in code contains no actual pane roster. If a source is down, the prior observations remain in the database with their original timestamps.

Enter each new direct quota observation through `./opsctl quota --provider codex|claude --pane PANE --left PERCENT --reset ISO_TIME --observed-at ISO_TIME --evidence SOURCE`. The Operations view refreshes its sourced Codex and Claude quota cards every minute; **Refresh data** fetches them immediately. Do not infer a Claude percentage from a Codex reading or from an owner statement without a dated, account-specific observation.

The private Operations view plots a rolling 24-hour history from
`GET /api/ops-metrics/history` and a seven-day verified strict-C checkpoint
history from `GET /api/ops-metrics/history?hours=168` (allowed range: 1–168 hours):
PM-reviewed strict full-C and verified-identity
observations, actual merge timestamps for the recent visible PR sample, and
working coder pane counts from successful collection runs. Missing samples are
not interpolated. Merge throughput and pane presence are engineering flow
signals, not deployments or verified productivity. Deployment frequency, change
failure rate, and recovery time remain unavailable until deployment and incident
records exist.

The executive C economics panel uses the latest published strict-C count and
working ceiling. The 24-hour credit delta requires a verified observation at
or before the 24-hour boundary, agreement between the latest manual credit
observation and published accounting, and an accounting sample no older than
60 minutes; otherwise it is unavailable. The credit card shows the accounting
sample age so a stale published count cannot appear as a measured zero-credit
day. The chart steps only at dated PM-reviewed credit observations. Its horizontal tail is
the last recorded value, not evidence of zero work in progress.
The C staffing line is a dated PM checkpoint: assigned lanes and authorized
compile/native slots are separate. Neither measures productive lane-hours.

The fixed subscription pool per calendar hour divides owner-reported monthly
subscriptions by hours in the current month. The interactive equal-allocation
figure divides that pool by a user-selected number of modeled C lanes, assuming
the entire pool supports those lanes during every calendar hour. It is a planning allocation, **not**
observed C spend per hour. Actual C spend requires C lane-hours, a billing
allocation, and usage charges. The milestone and cost figures use a selected
new verified functions per week; they are hypothetical scenarios, not an ETA.
The 24-hour signal pairs a comparable net credit count with 24 hours of fixed
pool commitment across all work; the latter is not attributable to C.
