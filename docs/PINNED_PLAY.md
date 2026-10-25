# Pinned Play (t140)

The default original-mode Play session uses
`~/.local/share/vp-of-agentry/dosbox-x-5a9c7c53/dosbox-x`. It is independent
of a producer lane's checkout. `VP_DOSBOX_X` overrides that executable.
Replacement mode defaults to the same executable, retains its separate
`VP_REPLACEMENT_DOSBOX_X` override and requires the reviewed registry/dispatch
assets. The `build` field still describes **dispatch mode**, not binary identity.

The installed binary is 62,790,864 bytes, advertises `2026.01.02 SDL2`, and has
SHA-256 `fc66e91e8e8d48cc0b176bc350febab753bff297f2d93fc6c1e9d1f21cb6efae`.
Its DOSBox-X source pin is `5a9c7c53481c2e933948039c33256776653f4faf`.
The normal core was rebuilt at `-O1 -g0`, and the linked C model closure at
`-O2`. Unchanged base-emulator objects were reused; this was not an independent
clean rebuild of every object.

The stable installation contains `provenance.json`, `README.txt`, the core/link
and model build logs, model-source hashes and the upstream `COPYING` file.
`provenance.json` records the exact core and link argv arrays, including their
configured include/link flags. Their command structure is:

```sh
make -C "$SOURCE/src/cpu" -j2 libcpu.a \
  CPPFLAGS="$CONFIGURED_CPPFLAGS -I$POOLRAD/include" \
  CXXFLAGS="$CONFIGURED_CXXFLAGS -O1 -g0"
make -C "$SOURCE/src" -j2 dosbox-x \
  LIBS="$CONFIGURED_LIBS $POOLRAD/resources/hybrid/pr_models.o"
```

The model closure and checkpoint-hook preparation are documented in Poolrad's
`docs/re/HYBRID_SAME_SAVE_PARITY.md`. The binary was copied byte-for-byte to the
stable location and its hash rechecked. Its version-only option exits with
status 1 while printing the expected banner; this is not a game launch.

The observer is inactive without `PR_HYBRID_REGISTRY`; dispatch is inactive
without a nonempty `PR_HYBRID_DISPATCH`; the checkpoint requires matching
`PR_PARITY_TARGET`, `PR_PARITY_PREFIX` and an arm file. Original-mode launches
clear the hybrid/checkpoint environment controls, including seed pins.

## Rollback

With the default `VP_PLAY_BUILD=original`, change one server environment value:

```sh
VP_DOSBOX_X=/usr/bin/dosbox-x
```

Apply it on the next server launch after the owner confirms the current game
has been preserved. Setting an environment variable does not change an already
running emulator. Replacement remains a separate opt-in experiment.

## Status contract

`GET /api/game/status` retains `build=original|replacement` and adds:

```json
{
  "emulator": {
    "kind": "checkpoint",
    "build_id": "dosbox-x-5a9c7c53-parity-o1",
    "sha256": "fc66e91e8e8d48cc0b176bc350febab753bff297f2d93fc6c1e9d1f21cb6efae",
    "release": "2026.01.02",
    "scope": "running_session"
  },
  "state_archive": {
    "status": "pending",
    "verified_count": 0,
    "archived_at": null
  }
}
```

Binary identity requires the known SHA-256; a filename or adjacent metadata
file does not establish it. An unrecognized binary has `kind=other` and null
build ID/release, retaining a measured SHA when available. A running session's
identity is frozen at successful launch. When stopped, `scope=next_start`
describes the configured next launch. The UI short hash is the binary SHA prefix
`fc66e91e`, not the source revision.

Archive status reads `VP_STATE_ARCHIVE_MANIFEST`, defaulting to
`$POOLRAD_REPO_DIR/resources/state-archives/manifest.json`. It does not create
an archive or read the old source runs. Missing manifest means `pending`.
`verified` requires schema 1, a timezone-qualified `created` timestamp,
`expected_count` equal to the nonempty `entries` list, and every entry's relative
`path`, positive `size` and `sha256` to match a distinct file inside the archive
directory. Missing, changed, duplicate or escaping files yield `unavailable`
with count 0. Only verified status supports an archived-state claim.

## Validation and remaining work

Synthetic tests cover hash-based identification, changed binaries, running
identity retention, missing identity, next-start semantics, one-variable
rollback and archive integrity failures. Native tagged-state validation is
pending and must be recorded before presenting the migration as ready for an
extended play session.

The 14 earlier owner states have **not** been archived or migrated. VP's
preservation hold remains in effect until the owner's in-progress-run answer
arrives. The old indices do not record a creator-binary hash; any attribution
to the system executable must retain that uncertainty. No old state is to be
edited, force-loaded or discarded.

NOT verified here: native save/load in both execution modes, live desk
audio/video, full-machine or full-game parity, complete C execution, or a clean
rebuild of all emulator objects. No replacement credit is claimed.
