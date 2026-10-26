# Theme authoring contract

Register a theme by adding only two files: <id>.css and <id>.json in this directory. The eager CSS/JSON globs discover them; do not edit main.jsx, a shared theme array, or another theme's files. IDs use lowercase letters, digits and hyphens and must match both filenames.

A manifest is {"id":"nostromo","name":"Nostromo","order":20}. Default is always first. Other entries sort by numeric order, then name, then ID as a stable tie-break. The registry rejects missing partners, mismatched IDs, empty names, nonnumeric order and a missing Default theme.

New theme CSS contains only token blocks, scoped to :root[data-theme="<id>"]. Inherit the Default tokens and override the roles needed by the theme. Do not add component selectors, layout rules, media queries, network font imports, animations or shared-file edits. This token-only rule applies to NEW themes: crt.css retains its pre-existing component, overlay and media rules unchanged as a fidelity exception.

Set bg, surface, surface-raised, ink, muted, accent, accent-contrast, borders and semantic colors; remap named component tokens when necessary. The contrast gate accepts opaque hexadecimal backgrounds and hexadecimal foregrounds with optional alpha; aliases may refer to other tokens. Unsupported token selectors or colors fail visibly.

The existing --overlay token carries CRT scanline strength through its rgba alpha (0.12), with a fixed 1px dark/3px clear pattern. Keep that legacy value unchanged. A new draft can declare --scanline-strength and consume it inside its own --overlay value, but that token alone does not enable an effect. Generic overlay, display-font and ChatScope body-font consumers are NOT implemented by this split: the existing effect selectors are CRT-only. Those consumers and CRT's dedicated strength-token migration need a separate implementation and verification; do not claim a new theme's overlay/font behavior from token presence alone.

Use system font stacks, or bundle an openly licensed font with its license text beside its font files in a theme-owned asset directory. Font assets/licenses may add files, but registration still needs only the CSS/JSON pair and no shared edit. Until generic font consumers exist, verify each actual font role in the browser and report unsupported ones.

Run from the repository root:

    .venv/bin/python tools/theme_contrast.py --json
    .venv/bin/python -m unittest tests.test_theme_contrast tests.test_theme_capture

Attach the gate report: ink/bg >=7, muted/bg >=4.5, accent/bg >=3, accent-contrast/accent >=4.5. These token checks do not certify every rendered text node, alpha overlay, focus outline or component.

Capture the actual theme with all dialogs closed at1067 and390, plus the owner1881 blocking widths1422/1067/960/800/700/390. Keep24x24 targets, unobscured keyboard focus,200% text, contrast4.5/3 and no clipping/overflow at blocking widths.320 is advisory: measure and name failures without treating them as blockers. Use the capture guard; a screenshot through an open Appearance dialog is invalid evidence.

Record CSS viewport size and raw devicePixelRatio. Viewport plus deviceScaleFactor1.8 is EMULATION, not proof of real browser zoom, operating-system scaling or physical-screen dimensions. Scanlines can rasterize differently across DPR values; report the configuration and inspect the actual result.

The stylesheet loader imports Default before the separate eager variant-glob module, at the original theme position between library and component CSS. main.jsx imports that loader and eagerly discovers the JSON manifests. This module boundary prevents Vite from hoisting the variant CSS before the existing library/default styles; adding a theme still changes only its own pair.
