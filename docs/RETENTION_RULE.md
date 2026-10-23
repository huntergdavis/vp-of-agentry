# Device and host space: retention rule

Written 2026-10-23 after the card fell to 451 MB free on a 99%-full 63 GB volume, and the owner
authorised log pruning. The lane implemented it; this is the summary a reader needs.

## Keep
- The most recent run of each kind.
- Anything cited in a doc, receipt, launch log, or inbox message from the last 48 h.
- Anything a lane may still be using, and **anything ambiguous — kept and listed as ambiguous**.
- Installs, fixtures, saves, registries and game assets are never in scope at all.

## Order of operations
1. Inventory and classify by **contents**, not by size or directory name.
2. Copy off the device.
3. `sha256` the copy **against the device original**.
4. Delete via a literal-path script that **re-hashes before each `rm`**, keeps on mismatch, and
   refuses while a game is running.
5. `df` before and after, **with wall-clock times**, labelled NET unless every writer was quiesced.
6. Stop at the target.

## The result that made the rule
`451 MB at 12:39:13 -> 1,720 MB at 12:46:09, NET +1,269 MB`, with the separate clean claim
`3,868 files / 1,319.9 MB archive-verified, then deleted`. No crackdown process at any of the
four checks; other lanes' non-game writes not excluded — hence NET, not "freed".

## Two things that look like logs and are not
- `/tmp/.../b2f28115-*` (419 MB, host): **9,321 `.c`/`.h` files and a thirdparty tree**. A checkout.
  Archived (117 MB, integrity-tested) and **not deleted**, because a checkout can hold unpushed work.
- Autostart screenshots cited in a doc: evidence. Kept.

*A directory that looks like logs by its size is not logs by its contents.*
