# Pinned Play (t140)

**Pinned opt-in hold:** the first native exercise saved a new tagged snapshot,
but both pinned-binary consumers exited 139 after reporting it loaded.
Do not switch Play or claim reliable restore from this result. The matched
system-binary control and crash backtrace are pending; old-state migration
remains held.

The default original-mode Play session remains on `/usr/bin/dosbox-x`.
The installed checkpoint executable at
`~/.local/share/vp-of-agentry/dosbox-x-5a9c7c53/dosbox-x` is independent of
a producer lane's checkout and requires an explicit `VP_DOSBOX_X` override.
Explicitly selecting `VP_PLAY_BUILD=replacement` also selects the pinned
executable, retaining its separate
`VP_REPLACEMENT_DOSBOX_X` override and requires the reviewed registry/dispatch
assets. The `build` field still describes **dispatch mode**, not binary identity.
Executable selection resolves once to an absolute path when the session
object is configured. Both identity hashing and launch use that path, so a
retained tmux PATH cannot select a different binary. An unresolved bare
override is rejected with a server-PATH configuration error.

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
rollback and archive integrity failures. The 42 focused backend tests passed,
including two different scripts on server versus retained-tmux PATHs in both
execution modes.

[Native v1 receipt](PINNED_PLAY_E2E_V1.json): the producer saved a 283,572-byte
new tagged snapshot with a passing ZIP CRC, no PR environment controls and no
observer output. Both consumers confirmed the native loader's `Loaded`
message, then exited **139 (SIGSEGV)** before reaching the restored route
gate or either checkpoint. Their driver phases exited 1. The producer's
emulator was terminated by the driver's normal cleanup after its successful
save; its driver phase exited 0.

The receipt is **FAIL, comparison_performed=false**. Native loader completion
does not establish successful resumed execution. No frame/register/VGA/RAM
comparison or reliable cross-process restore is established by this run.
The system control uses system binary `99d74601` to restore a byte-identical
copy of the **same pinned-produced snapshot**, with the same tag, transport,
normal core, keystrokes and route.
It requires native loading and survival through the post-load Right gate;
it makes no checkpoint/parity claim. That control is pending, followed by
two pinned-binary restore attempts of the same snapshot and a backtrace of
the original crash. A system failure would not by itself prove the pinned
binary innocent: the same state may expose a shared loader or capture defect.

The live Play implementation also creates Xvfb, rather than using a physical
desktop display. Its display is 800x600 with Xauthority; the probe uses
1024x768 through `xvfb-run`. Play uses tmux and PulseAudio when available;
the probe uses pipes and dummy audio. Play adds `-nomenu` and a 640x480 window
setting. The probe forces the normal CPU core in both consumers, whereas
Play explicitly selects it only for replacement mode. Original-mode Play
clears PR controls; the probe's original consumer enables the read-only
observer/checkpoint infrastructure. These differences remain material until
the crash is localized. This private failure alone does not establish
whether the live Play path would crash on load.

The private native exercise is `tools/pinned_play_probe.py`. Run it once
through the shared heavy-job wrapper with a fresh prefix and output path:

```sh
poolrad-heavy.sh python tools/pinned_play_probe.py \
  --poolrad-repo "$POOLRAD_REPO_DIR" --prefix t140-newtag-v1 \
  --output docs/PINNED_PLAY_E2E_V1.json
```

It creates a new tagged snapshot with PR controls absent, then restores
copies of that exact snapshot in original and replacement modes. It calls
the actual `GameSession.savestate` and `loadstate` methods, using disposable
Xvfb sessions. The private transport uses the R1 code-prompt gate in place
of the live desk's terminal startup marker; live tmux/UI transport is not
covered. Native load confirmation is still required, without forcing a
dialog. A baseline checkpoint after load and a checkpoint after Right
measure C returns during the restored route. The existing unmasked
comparator produces the receipt, including a FAIL if differences remain.
Raw state, frame and child-log files stay under ignored Poolrad resources.

The system control uses `--system-control --source-prefix t140-newtag-v1`,
a new run prefix and a separate receipt path. It checks the system binary
hash and restores a copy of the earlier producer snapshot without changing
the source. Two subsequent controls use `--pinned-control` with that same
source prefix and distinct run/output paths. None reads the old owner states.

The 14 earlier owner states have **not** been archived or migrated. VP's
preservation hold remains in effect until the owner's in-progress-run answer
arrives. The old indices do not record a creator-binary hash; any attribution
to the system executable must retain that uncertainty. No old state is to be
edited, force-loaded or discarded.

NOT verified here: successful resumed execution after native restore, live desk
audio/video, full-machine or full-game parity, complete C execution, or a clean
rebuild of all emulator objects. No replacement credit is claimed.
