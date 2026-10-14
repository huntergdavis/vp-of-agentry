# Operations metrics sources

The VP operations database is data/operations.sqlite3, which Git ignores. The file is mode 0600. The authenticated API is GET /api/ops-metrics; the local CLI is ./opsctl summary. Every record retains an observation time and source or evidence reference. A source outage is unavailable, never zero.

| Measure | Source and cadence | What it means | Limit |
| --- | --- | --- | --- |
| Pane staffing | Dunking Sheep panes, sampled each minute | Process presence by locally assigned role and reported state | Working, blocked, and done are terminal states, not verified productive work. |
| Recent PR state | Read-only GitHub PR list, at most every five minutes | Visible recent review and merge events | The last 100 PRs are a queue sample, not a whole-game completion denominator. Local unpublished work is absent. |
| VP message volume | Local VP messages SQLite, sampled each minute | Counts by channel and author role | Does not cover other conversations and stores no message text in the operations database. |
| Dunking Sheep flow | Aggregate metrics API, one-hour window at most every five minutes after daemon rollout | Message queue and handling counts with interval timestamps | Currently unavailable until the running daemon supports schema version 1. No message bodies, subjects, filenames, or account emails are accepted. |
| Weekly quota | VP direct /status observation, manually entered with pane, time, reset, and evidence | Percentage of the observed account's weekly allowance left | Stale readings remain labelled stale; panes sharing an account must be grouped by reset cohort. Burn is shown only after two direct readings at least 30 minutes apart with the same reset. |
| Local progress | PM-reviewed goal observations with evidence reference | Credited strict full-C functions and measured local queues | Provisional parity gates and queue starts do not add strict full-C credit. |
| Overall progress | PM-reviewed goal observations with evidence reference | Playable C demo gate and verified whole-game denominator | The playable demo is blocked until a same-state DOS/C frame; no verified whole-game denominator exists. |
| Money and tokens | No billing source connected | Unknown | Pane activity and quota percentage cannot be converted to token or dollar cost. |

The collector timer runs once per minute. GitHub and Dunking Sheep polling are throttled to five minutes. Roles are private local assignments entered with ./opsctl lane; the checked-in code contains no actual pane roster. If a source is down, the prior observations remain in the database with their original timestamps.
