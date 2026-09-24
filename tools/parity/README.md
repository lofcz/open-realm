# Parity harness

Tools for keeping the reimplementation visually faithful to the original
Warcraft III, and for catching rendering regressions.

## Linux retail comparison with Wine

`wc3.sh` launches retail or OpenRealm against the same installation and optional map, in a window. It records
the command, edition, map, source revision/dirty files, Wine version, and process output under `build/parity/logs/`.
Retail requires your own installed executable and archives. No disassembler or debugger is required.

```bash
export WC3DATA='/path/to/Warcraft III'
# TFT Night Elf 1 (Maiev), as distinct from ROC Night Elf 1 (Tyrande):
tools/parity/wc3.sh retail tft 'Maps/FrozenThrone/Campaign/NightElfX01.w3x'
tools/parity/wc3.sh openrealm tft 'Maps/FrozenThrone/Campaign/NightElfX01.w3x'
# Reign of Chaos:
tools/parity/wc3.sh retail roc 'Maps/Campaign/NightElf01.w3m'
tools/parity/wc3.sh openrealm roc 'Maps/Campaign/NightElf01.w3m'
# Omit the map to use the menus; print commands without launching:
WC3_DRY_RUN=1 tools/parity/wc3.sh retail tft
```

Build the native executable first with `make BUILD=release FFMPEG=1 openwarcraft3`. `WC3_BINARY` can select a
different build. Install Wine with your distribution's package manager (Arch/CachyOS: `sudo pacman -S wine gst-plugins-good`).
Wine's AVI demuxer may also need `gst-plugins-good`; a `Missing decoder: Audio Video Interleave` log means movie
playback cannot be used as evidence yet. Use a consistent retail patch and locale for each comparison.

The default prefix is `${XDG_DATA_HOME:-$HOME/.local/share}/open-realm/wine-wc3`, separate from `~/.wine`.
`WINEPREFIX` and `WINE` override the prefix and runner. Modern Wine can run the 32-bit game in its default
64-bit/WoW64 prefix; do not force `WINEARCH=win32` on a WoW64-only distribution build.
See the upstream [Wine manual](https://man.archlinux.org/man/wine.1.en) for prefix and argument semantics.
The launcher targets the classic `war3.exe` installation layout (locally exercised with 1.27b), uses `-classic`
for ROC, and passes archive-relative map paths to `-loadfile`. It does not install games, alter archives, or
unlock campaign progress. Retail can write its normal settings, saves, and replays in the installation/prefix.

On CachyOS with Wine 11.17, Warcraft III 1.27b build 7085 reached NightElfX01's loading screen and
`PRESS ANY KEY TO CONTINUE` using the default renderer after installing the AVI plugin. The initial run with
forced OpenGL and missing AVI support crashed in `Game.dll`; that run is not a valid reference result. The
launcher therefore leaves the renderer at its default. `WC3_RENDERER=opengl` explicitly opts into the alternate
path for separate compatibility testing. A successful loading screen proves startup/map loading, not audio or
gameplay fidelity. Warcraft's own crash reports are under
`$WINEPREFIX/drive_c/users/<user>/AppData/Local/Temp/BlizzardError/<timestamp>/Crash.txt`.

For bark comparisons, record both runs with desktop audio and perform the same short sequence after skipping
the intro: select one unit, wait for speech to finish, issue one ground move, then repeat moves while it speaks.
Repeat with a mixed selection, changing the focused subgroup, and with an attack order. Record speaker, response
category, overlap/interruption, and order acceptance separately. Keep sound/music volume, camera position,
selection, and elapsed time comparable; random line identity need not match. Save a retail game just after the
intro for fast manual repetition, and keep native/retail saves separate.

The logs capture diagnostics, not audio. Use OBS or your desktop recorder for audible evidence. When an observed
difference becomes understood, encode it in a fixture-backed regression; do not replace the automated tests with
repeated manual launches. Existing sound-path regressions and known limits are documented in
[WC3 sounds](../../games/warcraft-3/sounds.md).

## 1. `shot.sh` — live window capture (macOS)

Launches a client, captures its GL window to a PNG by window-id (reliable even
when the window is occluded), then kills it.

```sh
tools/parity/shot.sh --app ours   --screen menu_main -o /tmp/ours.png
tools/parity/shot.sh --app legacy                    -o /tmp/legacy.png
tools/parity/shot.sh --app both   -o /tmp/parity.png   # ours + Legacy, side by side*
```

`--app both` writes `*-ours.png` and `*-legacy.png`; if ImageMagick's `montage`
is installed it also writes `*-sidebyside.png`. Options: `--data <dir>`,
`--screen <menu_cmd>`, `--delay <sec>`, `--keep`.

The Legacy client is the original at
`/Applications/Warcraft III (Legacy)/Warcraft III.app` (v1.29.2) — the parity
reference.

## 2. `render_golden.sh` — golden-image regression test

Renders each model in `golden_manifest.txt` to a **deterministic** PNG via
`mdxtool -o` (fixed frame + seeded particle RNG) and
compares it to a committed reference in `golden/` with `imgdiff`. Fails if any
render drifts beyond the mean-pixel-difference threshold.

```sh
make test-render-golden        # compare against golden/ (exit non-zero on drift)
make update-render-golden      # regenerate golden/ after an intentional change
# or directly:
tools/parity/render_golden.sh --repeat --data "$WC3DATA"
# Focused manifest, bounded per-render execution:
tools/parity/render_golden.sh --manifest /path/to/case.txt --repeat --timeout 60 --data "$WC3DATA"
```

This requires a display/GL (mdxtool opens a window), so it is **opt-in** and not
part of `make test` (CI is headless).

### Manifest format

`name | mpq | model | extra mdxtool args` — one render per line. Pick models
self-contained in one archive that exercise distinct renderer paths (flipbook
water, team color, particles, geometry). Glue scenes need `--use-model-camera`;
units use the default fitted orbit camera.

Each invocation retains its manifest, revision information, commands, renderer logs, images, and
comparison output in a unique `build/parity/render-XXXXXX/` directory, printed at startup.
GNU `timeout` (or `gtimeout` from coreutils on macOS) bounds each render to 60 seconds by default,
with a five-second kill grace period. Archives are resolved by their actual filename, including
case differences and an expansion subdirectory; ambiguous matches fail explicitly.

`--repeat` renders every case twice and requires exact decoded pixel equality before comparing
or updating a reference. This checks repeatability on the current machine, not equivalence across
GPU/driver versions. A repeat failure, failed render, missing output/reference, or empty manifest
is a failure. Update mode also returns failure when a render fails; it may already have updated
preceding successful cases. Review the diff before accepting any reference changes. A reference
image records accepted behavior; it is not evidence that behavior matches retail.

`make test-render-harness` exercises failure propagation using fake renderer/comparator processes,
without retail data or GL. It is included in `make test`. The actual image suite remains opt-in.
For the current baseline and the NightElfX01 investigation, see
[renderer verification](../../docs/renderer-verification.md).

## Live render inspection

Source `tools/parity/render_inspect.py` in GDB attached to a matching debug build, then run
`render-dump /tmp/render.json` and detach. It reads camera, entity/model identities, and exact
animation frames without calling code in the process. Replay a submitted frame with
`mdxtool --raw-frame <frame> --background 808080 --dump-all -o /tmp/repro.png`.
See [renderer verification](../../docs/renderer-verification.md#inspecting-a-live-rendering-failure)
for symbol requirements, limitations, and the confirmed NightElfX01 case.

## Pieces

- `mdxtool -o <png> [--frame <ms>] [--seed <n>]` — deterministic clean render to
  PNG (in `tools/mdxtool.c`). `--background 808080` exposes black opaque geometry
  that can disappear against the default black clear color.
- `imgdiff a b [--threshold m] [--pixel-tol t] [--diff out.png]` — image compare
  (in `tools/imgdiff.c`; standalone, stb-only).
- `golden/` — committed reference PNGs (regenerate with `--update`).
