# Renderer verification and incident evidence

## Acceptance layers

Use the existing headless model/shadow tests for parsing, animation, lifetime, shader submission,
and geometry contracts. Use `mdxtool` for isolated GL output and the parity harness for retained,
repeatable captures. Only then compare the affected mission with retail. These are distinct checks:
passing numeric tests does not prove visual correctness, and matching an old screenshot does not
prove retail fidelity.

```bash
make BUILD=release FFMPEG=1 test-render-harness test-renderer-model test-renderer-shadows
make BUILD=release FFMPEG=1 mdxtool imgdiff
# Requires local retail archives and a GL display; two captures per case:
tools/parity/render_golden.sh --repeat --data "$WC3DATA"
make BUILD=release FFMPEG=1 TEST_JOBS=8 test
```

The [parity README](../tools/parity/README.md) describes retained evidence, Wine comparisons,
focused manifests, timeout behavior, and explicit reference updates. Do not regenerate references
just to make a comparison pass. Record asset version, camera, sequence/frame, seed, background,
renderer/driver, and source revision before interpreting a difference. Renderer startup logs record
the GL implementation. Retail archives remain local; automated tests use generated fixtures.

## Baseline audit, September 2026

The audit exposed and reproduced three infrastructure defects:

- Three ribbon tests freed stack-backed model state without calling `MDLX_ForgetRibbonModel`.
  The registry introduced with detached ribbons (`da272817`) retained those model addresses;
  the subsequent orphan tick crashed. Fixture cleanup now matches production model unloading.
- Standalone `mdxtool` supplies no cvar registry. Video startup called the missing `CvarString`
  callback directly (`vid_modes`, introduced in `8204597d8`; also the macOS hidden-window branch).
  The existing `R_CvarEnabled` helper enabled every flag when no callback existed. Startup now
  uses that helper, and the helper honors the supplied default. The absent-host regression failed
  on both default-off assertions before the fix. These defaults are part of the host API contract,
  not substitute game data.
- The golden runner returned success for empty manifests and failed reference-update runs,
  skipped a final line without a newline, and deleted failure logs. Headless process tests now
  cover these cases, repeat failures, timeouts, comparisons, and archive filename resolution.

Model and shadow suites pass 5,364 assertions each (103 tests) locally after these fixes.
The five existing golden cases each produced identical decoded pixels on repeat runs on Intel ARL,
Mesa 26.2.3, SDL2-compat 2.32.72, Wayland. Four differed from the committed references: both menu
scenes, Peon, and Footman. The expansion logo was within the existing mean-difference threshold.
The reference images were not updated. These differences need interpretation against their original
capture conditions; they do not by themselves identify a new renderer regression.

The aggregate suite is **not green** on this host: the WC3 engine process crashes in the SDL
text-input injection test. A standalone SDL2 program reproduces the crash by initializing
`SDL_INIT_EVENTS` and pushing `SDL_TEXTINPUT` with `text="test"`; the stack enters SDL3 through
SDL2-compat. Direct queue insertion avoids the push crash but subsequently crashes while polling,
and initializing dummy video did not solve it. No event was removed from the engine test and no
conditional skip was added. Resolve the SDL compatibility issue before treating the aggregate run
as a passing acceptance gate. The standalone probe is retained so this can be verified independently:

```bash
cc tools/parity/sdl_textinput_probe.c -o /tmp/sdl-textinput-probe $(pkg-config --cflags --libs sdl2)
/tmp/sdl-textinput-probe
```

On a working SDL implementation it exits zero; on the observed compatibility build it exits by
SIGSEGV. It is a diagnostic probe, not a test to skip or mark as an expected failure.

## NightElfX01 black-plane investigation

The reported scene is TFT `Maps/FrozenThrone/Campaign/NightElfX01.w3x`, during the Huntress
Wildkin dialogue near waterfalls and burning structures. In the supplied 1.27b installation,
that map is in `War3xlocal.mpq`. Missing `Melee_V1` overlay messages and sound diagnostics do not
identify the black polygon's producer.

The root cause is doodad spawn lifecycle, not blending. `SP_SpawnDoodad` registered the model
but left its animation unset and absolute frame at zero. The intact building and Ruined1 have Stand at
4167–6667 and Portrait at 67333–69333. Ruined2 has Birth first and Stand at 61667–66667. Their second geoset is the portrait backdrop (bone
`PortraitBackground`, opaque material 1): its static alpha is 1, but its authored alpha track hides
it during Stand. At frame zero, outside the sequences, the static value is used and the large
backdrop appears in the world. Normal `mdxtool --frame 0` did not reproduce this because it maps
relative time into Stand. `--raw-frame 0` reproduces the submitted pose exactly.

The live inspection identified these placements in the reported view:

| Entity | Model | Origin | Observed frame |
|---|---|---|---|
| 3977 | ElvenFishVillageBuilding0 (`ASv0`) | -4032, -3200, 111 | 0 |
| 1089 | ElvenFishVillageBuildingRuined1 | -4480, -3200, 67.5 | 0 |
| 1088 | ElvenFishVillageBuildingRuined2 | -4800, -3456, 56.25 | 0 |

Correcting the live server frames removed the planes; screenshots were captured before and after.
Building0 and Ruined1 use frame 4167. Ruined2 was initially inspected at 4167 (inside its Birth),
then corrected to its actual Stand frame 61667. The permanent fix resolves Stand by name per model. This was an instance-level diagnostic correction, not a hot replacement of the game
module. The permanent fix starts Stand through `G_DoodadSetAnimation` at spawn, sharing the normal
animation clock, loop handling, and script overrides. Doodads with no resolved animation remain
static. New map loads use the fix; old frame-zero instances are not implicitly migrated on load.

`wc3_doodad.spawn_enters_nonzero_stand_and_script_can_replace_it` drives `SP_CallSpawn` with a
synthetic `ASv0`/`ASx2` SLK rows and generated MDX files at the authoritative model paths.
The second model puts Birth before Stand to reject a sequence-zero assumption. It failed four spawn
assertions before the fix. It checks initial frame, animation clock, looping, and script replacement.
The generated fixture needs no retail data. All six doodad tests pass 37 assertions in both ROC and TFT modes. The broader WC3 suites passed
34,023 assertions per edition before adding the second fixture variant; the aggregate suite still
hits the separately documented SDL compatibility crash. Isolated retail captures verify the actual portrait
geoset: sampled alpha is 1 at frame 0 and 0 at frame 4167.

```bash
model='Buildings\Other\ElvenFishVillageBuilding0\ElvenFishVillageBuilding0.mdx'
# Use the actual expansion archive filename from the installation:
timeout 15 build/bin/mdxtool -mpq "$WC3DATA/War3x.mpq" -model "$model" \
  --raw-frame 0 --background 808080 --dump-all -o /tmp/plane-before.png
timeout 15 build/bin/mdxtool -mpq "$WC3DATA/War3x.mpq" -model "$model" \
  --raw-frame 4167 --background 808080 --dump-all -o /tmp/plane-stand.png
```

`--raw-frame` applies to rendering and the loaded-model `--dump-all` sample. `--info` remains a
no-window binary inspection mode; use `--dump-all -o` for evaluated geoset alpha. A gray background
exposes an opaque backdrop even when its replaceable texture is white in the isolated viewer.
The relevant property is its visibility, not the difference between the viewer's and scene's color.

## Inspecting a live rendering failure

`tools/parity/render_inspect.py` adds the read-only GDB command `render-dump`. It makes no calls
inside the inferior and does not change game state. Attach pauses the process; detach promptly.
Use debug symbols and libraries from the exact running build, including the same game and build
options. Do not reuse addresses from another process or infer struct layouts from a newer build.

```text
gdb -p <pid>
(gdb) source tools/parity/render_inspect.py
(gdb) render-dump /tmp/render.json
(gdb) detach
(gdb) quit
```

Linux ptrace policy may require launching the game as GDB's child or attaching with elevated
permissions. Do not change global ptrace policy. The JSON records the last submitted view's camera,
time, entity numbers, origins, flags, model identities, sequence ranges, and current/previous frames.
When matching symbols expose `mod_known`, it includes cached asset paths. An unavailable registry
is an explicit warning; internal MDX names are not archive paths. Verify that the recorded camera
and entity count correspond to the world view you are investigating. This is a submission snapshot,
not a GPU draw capture or proof that every submitted entity was drawn.

For advanced symbol-assisted inspection, the optional second argument is a quoted expression
pointing to the running `struct render_globals`. This supports an explicitly validated live address
when only type information is available. The command does not validate ABI compatibility for you.
The NightElfX01 investigation captured 2,562 submissions and 114 unique models this way.

Filter the JSON by model or position, resolve the actual archive path, and replay the recorded
absolute frame with `mdxtool --raw-frame`. Confirm the responsible geoset/material with the loaded
model dump, then add a regression at the state producer. A frame dump alone does not include full
particle history, fog, or all material uniforms; preserve those conditions when the bug requires them.

See [diagnostic tools](diagnostic-tools.md), [renderer backend](renderer-backend.md),
[doodad animation](games/warcraft-3/doodad-animation.md), and
[test-first verification](../CONTRIBUTING.md#test-first-behavior-verification).
