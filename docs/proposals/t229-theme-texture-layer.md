# Theme texture layer — proposal (owner #1980)

Status: **proposal only, no implementation.** One worked example is specified at the end and is **not yet prototyped**; nothing in `web/src` is touched by this document.

Today the themes are colour schemes. This proposes a *surface character* layer: named effect slots a theme may set, defaulting to none, so a theme that does not care stays exactly as flat as it is now.

## 1. Effect slots (the whole surface vocabulary)

Each slot is a CSS custom property set per theme in that theme's own stylesheet. A theme that omits a slot gets the initial value below. No component CSS is ever edited to add an effect — the same rule as the tokens.

| slot | what it is | initial value | layer |
|---|---|---|---|
| `--surface-texture` | tiling pattern on page background (`background-image`) | `none` | page |
| `--panel-texture` | pattern on panels/cards | `none` | panels |
| `--overlay-grain` | static noise overlay, one image, no animation | `none` | page (over content, under text) |
| `--overlay-scanline` | repeating-linear-gradient rows | `none` | page |
| `--edge-wear` | inset shadow / border irregularity on panel edges | `none` | panels |
| `--glow` | outer shadow colour strength for active elements | `none` | controls |
| `--texture-anim` | animated variant (e.g. glyph rain), **off unless a theme opts in** | `none` | page |

Why slots rather than per-theme hacks: the contrast and performance gates below have to be enforceable. A rule that can be stated once ("a textured surface must not reduce measured text contrast below the gate") can be checked against seven named slots; it cannot be checked against twelve bespoke CSS blocks.

## 2. Per-theme proposals

Intensity range is given as *subtle → strong* so a theme can be dialled without redesign.

| theme | texture idea, one sentence | made of | applies to | intensity |
|---|---|---|---|---|
| **Default** | Stays flat: Default is the reference surface every contrast measurement is compared against. | — | — | none |
| **1980s CRT** | The phosphor screen: scanlines plus a faint vignette, no moving parts. | `--overlay-scanline` (repeating gradient), `--glow` | page, controls | subtle → medium |
| **Nostromo** | Industrial grime: grain and worn panel edges, the feel of a hull that has been repaired. | `--overlay-grain`, `--edge-wear` | panels, page | subtle → medium |
| **2001** | Stays flat: the fiction is a pristine white surface; any grain contradicts it. Allowed at most a barely-visible `--glow` on active controls. | — | — | none |
| **Metropolis** | Art-deco machine age: hard geometric panel rules, no noise at all. | `--edge-wear` (crisp, not gritty) | panels | subtle |
| **Forbidden Planet** | Cold instrument glow: a soft bloom behind headers, no surface grain. | `--glow` | header | subtle |
| **Blade Runner** | Rain on glass and neon bleed: animated glyph-free rain streaks, the one theme that wants motion. | `--overlay-grain`, `--texture-anim` (rain) | page | medium → strong |
| **Tron** | Grid light: a faint perspective grid, animated by a slow sweep. | `--surface-texture`, `--texture-anim` (sweep) | page | subtle → medium |
| **Imperial** | Heavy institutional: embossed panel edges, no noise. | `--edge-wear` | panels | subtle |
| **Dune** | Sand: wind-rippled texture on the page, drifting very slowly. | `--surface-texture` (SVG turbulence), `--texture-anim` (drift) | page | medium |
| **LCARS** | Stays flat: LCARS is a clean control panel; texture would read as damage. Panel blocks may use `--edge-wear` only. | — | — | none |
| **WarGames** | Cold-war terminal: scanlines and a hard horizon glow, static. | `--overlay-scanline`, `--glow` | page, header | subtle |

## 3. Themes that should stay flat, and why

* **Default** — it is the control surface: every pixel-contrast comparison in the repo is against Default. Texturing it destroys the baseline.
* **2001** — the whole aesthetic is an unmarked white plane. Grain or scanlines turn "pristine" into "damaged screen".
* **LCARS** — a designed control panel with its own dense geometry; any texture competes with the panel blocks and reads as wear on a system that is supposed to look maintained.

A proposal that textures all twelve is a proposal that has not looked at the themes. Three flat, one (Metropolis/Imperial) texture-on-edges-only, and motion in exactly two (Blade Runner, Tron) plus one slow drift (Dune) is the honest distribution.

## 4. Cost, reduced motion, DPR — per effect

| effect | cost | `prefers-reduced-motion` | DPR behaviour |
|---|---|---|---|
| `--overlay-scanline` | static image, one paint; **halves in apparent strength at DPR2** because the physical row doubles — state a `2px` step at DPR1 and `4px` at DPR≥2 so the look is constant | none needed (static) | must be stepped, not scaled |
| `--overlay-grain` | one tiled PNG/SVG, one paint; no repaint on scroll if `background-attachment: fixed` is avoided | none needed | grain must be regenerated or scaled by an integer factor, or DPR2 turns 1px noise into 2px blur |
| `--surface-texture` (SVG turbulence) | rasterised once per size; measurable first-paint cost, record it | static variants unaffected | re-rasterise per DPR or accept softness — state which |
| `--edge-wear` | zero extra cost (shadow/border only) | none needed | 1px borders must not round to 0 at DPR1.8 |
| `--glow` | cheap shadow; avoid `filter: blur()` on large areas | none needed | shadow spread is in CSS px, so it scales correctly |
| `--texture-anim` (glyph rain / rain / drift / sweep) | **composited only**: `transform`/`opacity` on a single fixed layer, no per-frame JS; measure frame time in the heavy queue and record it | **off by default**; must honour `prefers-reduced-motion: reduce` by not starting at all (not by "reducing speed") | animation distance scales with DPR; keyframes in `%` so the loop is size-independent |

Hard constraints restated, because each has already been violated somewhere in this fleet once: no network requests (CSS/SVG data URIs or locally shipped licensed files, same rule as fonts); text contrast must be measured with the **pixel-contrast layer**, not the token gate, on every textured surface; animation opt-in and off by default; performance measured via transform/opacity only; DPR behaviour stated per effect rather than discovered later; effects set through named slots only.

## 5. Worked example — Dune + static sand (PROTOTYPED, measured)

Page: `prototype/dune-sand.html`. **Off by default** — the texture applies only with `?texture=dune-sand`; with no flag the page is the flat palette. One slot is used (`--surface-texture`) as an inline SVG `feTurbulence` data URI: **no network request**, no shipped binary, no component CSS touched.

Captures (dialog closed, DPR 1.8, one heavy-queue job): `dune-off-1067.png`, `dune-on-1067.png`, `dune-off-390.png`, `dune-on-390.png`.

**Rendered pixel contrast** on the painted pixels of the body-text element (element screenshot → canvas `getImageData` → WCAG relative luminance; darkest 2% = background, lightest 2% = ink):

| width | texture | background (darkest 2%) | ink (lightest 2%) | ratio |
|---|---|---|---|---|
| 1067 | off | `[42,33,24]` | `[241,229,207]` | **12.68:1** |
| 1067 | on | `[46,37,28]` | `[241,229,207]` | **12.06:1** |
| 390 | off | `[42,33,24]` | `[241,229,207]` | **12.68:1** |
| 390 | on | `[46,37,28]` | `[241,229,207]` | **12.06:1** |

The sand costs **0.62 of contrast** (12.68 → 12.06, ~5%): it lifts the background's darkest pixels from `[42,33,24]` to `[46,37,28]` while the ink is unchanged, and both widths stay far above the 4.5:1 body-text gate. That is the number to watch per theme — **a texture that lightens a dark ground eats contrast**.

Effect notes for this one: static image, one paint, **no animation** (reduced-motion is a no-op here); DPR behaviour is per-CSS-pixel rasterisation, so it does not double the way scanlines do; no frame cost because nothing animates.

**Limits**: the page mirrors the Dune palette and the slot mechanism, not the desk bundle — it proves the effect and the measurement, not the integration. The percentile method reports extreme pixels (a mean-based measure would be slightly lower), and the measurement is DPR 1.8 only.
