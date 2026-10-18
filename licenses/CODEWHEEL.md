# Private code-wheel illustrations

The optional 72 GIFs (`esp01.gif`–`esp36.gif`, `det01.gif`–`det36.gif`) are
reference illustrations from Dave Kennedy's Pool of Radiance code wheel,
which credits Andrew Schultz for the lookup work:
https://dkennedy.io/por-code-wheel/wwm.html

The local source project's `licenses/CODE_WHEEL_ARTWORK.md` and
`docs/RESEARCH.md` section 6 do not grant redistribution rights. The original
artwork remains the property of its respective rights holders. This notice
does not grant a license to it. The desk's code license does not cover it.

Keep personal copies in ignored `data/codewheel/` (or the private directory
configured by `VP_CODEWHEEL_DIR`). Do not add the GIFs, extracted pixel data,
game frames, or generated private comparison fixtures to Git or `web/public`.
Only authenticated, allowlisted `/api/game/codewheel/{filename}` routes serve
these files. They are not included in the frontend bundle.
