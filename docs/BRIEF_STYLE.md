# Owner brief style (owner directive, 2026-10-20, web message #1083)

> "These briefs are too technical. I need higher level language, plain language
> descriptors, bullet points, ASCII art and easy easy please."

This is a standing rule for **every** brief posted to the owner through
`vpctl brief --channel vp`. It applies to every model and harness that takes the
VP role, not just the one that received the directive.

## Rules

1. **Lead with what happened, in plain words.** "The game draws the screen twice"
   beats "duplicate tile replay across two render passes". If a sentence needs a
   hex address to be true, it belongs in the repository, not in the brief.
2. **No hex, no mnemonics, no file paths, no function ids in the owner brief.**
   Name things by what they do: "the quit routine", "the disk-open call". Addresses
   and ids go in the PRs and evidence docs where they are checked.
3. **Bullet points, short lines.** Long paragraphs are where technical briefs hide.
4. **Use ASCII art for anything with structure**: before/after, a pipeline, a
   progress bar, a split, a budget. One diagram beats a paragraph of numbers.
5. **Give the number that matters and say what it means.** "18-19 ms of the ~33 ms
   we need" is usable; "18.44-18.49 FPS ceiling at 75% internal" is not.
6. **Progress bars for slow grind work:**
   `[#########-------------------------]  252 of 815 bodies  (31%)`
7. **State corrections plainly and take them yourself.** If a previous brief was
   wrong, say so in the next one, in the same plain register, without hedging.
8. **Always end with one of two lines:** what needs the owner's decision, or
   "nothing needs you tonight". Never leave the owner guessing which.
9. **Keep it short.** Under ~350 words including the diagrams. If it needs more,
   it is two briefs or it belongs in a document.

## Contrast (same fact, two registers)

Too technical:
> `SHAPE_UNSTABLE` by R3; timing discarded; tile1 mean 1648.5 vs tile2 mean 1450.5;
> classifier `scissor < viewport` swept interleaved 2x draws.

Plain:
> The first test failed - and the fault was in our own measuring code, not the game.
> Fixed, re-measured, and the two halves now match 99.6% of the time.

## Enforcement

The style is checked by reading the brief before posting: if it contains a hex
literal, a function id (`OVL_...`, `RES_...`), a file path, or a raw mnemonic, it is
not ready. Technical evidence stays in the PR, the evidence doc, and the task board.

## Cadence (owner directive #1158, 2026-10-21)

> "Change your update cadence to once every 4 hours for the regular reports, i'm
> getting far, far too many reports"

Rules:
- **Regular/status briefs: every 4 hours.** Both automatic report schedules (`d55`
  VP check-in, `d60` crew check) run at `240m`.
- **A brief is still sent immediately, outside the cadence, for exactly four things:**
  a decision the owner must make, a failure that changes what he can rely on, an
  answer to a question he asked, or a correction to something already sent him.
  Nothing else justifies an early brief.
- Work that needs no owner input is reported **in the next scheduled brief**, not
  as its own message.
- The cadence applies to the **owner channels**. Agent inbox traffic and the task
  board are unaffected: keep those dense.
