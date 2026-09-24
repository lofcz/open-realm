#!/bin/bash
#
# render_golden.sh - golden-image regression test for the MDX renderer.
#
# Renders each model in golden_manifest.txt to a deterministic PNG (via
# `mdxtool -o`, fixed frame + seeded RNG) and compares it to a committed
# reference under tools/parity/golden/ using `imgdiff`. Fails (non-zero exit)
# if any render drifts beyond the threshold.
#
# Usage:
#   tools/parity/render_golden.sh [--update] [--repeat] [--manifest <file>] [--data <dir>]
#     --update        (re)generate the golden references instead of comparing
#     --threshold T   mean abs per-channel diff allowed (default 2.0)
#     --data <dir>    data dir (default: data/Warcraft III)
#     --manifest <f> use a focused case manifest
#     --repeat        render twice; require exact image equality before accepting
#     --timeout <s>   per-render time limit (default 60 seconds; GNU timeout)
#
# Requires a display/GL (mdxtool opens a window) -> run locally, not in headless CI.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PARITY="$REPO/tools/parity"
GOLDEN="$PARITY/golden"
MANIFEST="$PARITY/golden_manifest.txt"
MDXTOOL="$REPO/build/bin/mdxtool"
IMGDIFF="$REPO/build/bin/imgdiff"
DATA="$REPO/data/Warcraft III"
THRESHOLD=2.0
UPDATE=0
REPEAT=0
LIMIT=60

while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="${2:?--manifest needs a file}"; shift 2;;
    --update) UPDATE=1; shift;;
    --repeat) REPEAT=1; shift;;
    --timeout) LIMIT="${2:?--timeout needs seconds}"; shift 2;;
    --threshold) THRESHOLD="${2:?--threshold needs a number}"; shift 2;;
    --data) DATA="${2:?--data needs a directory}"; shift 2;;
    -h|--help) sed -n '2,19p' "$0"; exit 0;;
    *) echo "render_golden.sh: unknown arg '$1'" >&2; exit 2;;
  esac
done

[ -x "$MDXTOOL" ] || { echo "missing $MDXTOOL — run 'make mdxtool'" >&2; exit 2; }
[ -x "$IMGDIFF" ] || { echo "missing $IMGDIFF — run 'make imgdiff'" >&2; exit 2; }
TIMEOUT="$(command -v timeout || command -v gtimeout)" || {
  echo "render_golden: GNU timeout is required (coreutils)" >&2; exit 2;
}
[[ "$LIMIT" =~ ^[0-9]+([.][0-9]+)?$ ]] && awk "BEGIN {exit !($LIMIT > 0)}" || {
  echo "render_golden: timeout must be positive seconds" >&2; exit 2;
}
mkdir -p "$GOLDEN" "$REPO/build/parity"
WORK="$(mktemp -d "$REPO/build/parity/render-XXXXXX")"
echo "render_golden: evidence in $WORK"
cp "$MANIFEST" "$WORK/manifest.txt"
{ git -C "$REPO" rev-parse HEAD; git -C "$REPO" diff --stat; } > "$WORK/revision.txt" 2>&1 || true

pass=0; fail=0; updated=0
while IFS= read -r line || [ -n "$line" ]; do
  # strip comments / blank lines
  line="${line%%#*}"
  [ -z "${line// }" ] && continue

  name="$(echo "$line"  | awk -F'|' '{gsub(/^ *| *$/,"",$1); print $1}')"
  mpq="$(echo "$line"   | awk -F'|' '{gsub(/^ *| *$/,"",$2); print $2}')"
  model="$(echo "$line" | awk -F'|' '{gsub(/^ *| *$/,"",$3); print $3}')"
  extra="$(echo "$line" | awk -F'|' '{gsub(/^ *| *$/,"",$4); print $4}')"
  [ -z "$name" ] && continue

  out="$WORK/$name.png"
  ref="$GOLDEN/$name.png"
  archive="$DATA/$mpq"
  # Windows installs vary in filename case and expansion subdirectory layout.
  if [ ! -f "$archive" ]; then
    matches=()
    while IFS= read -r -d '' candidate; do matches+=("$candidate"); done < <(
      find "$DATA" -maxdepth 2 -type f -iname "$mpq" -print0
    )
    if [ "${#matches[@]}" != 1 ]; then
      echo "ARCHIVE-FAIL $name: expected one $mpq in $DATA, found ${#matches[@]}"
      fail=$((fail+1)); continue
    fi
    archive="${matches[0]}"
  fi

  read -r -a extra_args <<< "$extra"
  command=("$MDXTOOL" -mpq "$archive" -model "$model" --frame 1000 --seed 1234 "${extra_args[@]}")
  printf '%q ' "${command[@]}" -o "$out" > "$WORK/$name.command"
  if ! "$TIMEOUT" -k 5 "$LIMIT" "${command[@]}" -o "$out" >"$WORK/$name.log" 2>&1; then
    echo "RENDER-FAIL $name"; tail -3 "$WORK/$name.log" | sed 's/^/    /'; fail=$((fail+1)); continue
  fi
  if [ ! -f "$out" ]; then
    echo "RENDER-FAIL $name (no output)"; fail=$((fail+1)); continue
  fi

  if [ "$REPEAT" = 1 ]; then
    if ! "$TIMEOUT" -k 5 "$LIMIT" "${command[@]}" -o "$WORK/$name.repeat.png" >"$WORK/$name.repeat.log" 2>&1 ||
       ! "$IMGDIFF" "$out" "$WORK/$name.repeat.png" --threshold 0 --diff "$WORK/$name.repeat.diff.png" >"$WORK/$name.repeat.cmp" 2>&1; then
      echo "REPEAT-FAIL $name"; fail=$((fail+1)); continue
    fi
  fi
  if [ "$UPDATE" = 1 ]; then
    cp "$out" "$ref"; echo "UPDATED  $name -> $ref"; updated=$((updated+1)); continue
  fi
  if [ ! -f "$ref" ]; then
    echo "NO-GOLDEN $name (run with --update to create $ref)"; fail=$((fail+1)); continue
  fi
  if "$IMGDIFF" "$ref" "$out" --threshold "$THRESHOLD" --diff "$WORK/$name.diff.png" 2>"$WORK/$name.cmp"; then
    echo "PASS     $name   $(sed -n 's/.*mean=/mean=/p' "$WORK/$name.cmp")"; pass=$((pass+1))
  else
    echo "FAIL     $name   $(sed -n 's/.*mean=/mean=/p' "$WORK/$name.cmp")"
    fail=$((fail+1))
  fi
done < "$MANIFEST"

echo "----"
if [ "$UPDATE" = 1 ]; then
  echo "render_golden: updated $updated reference(s) in $GOLDEN"
fi
if [ "$((pass+fail+updated))" = 0 ]; then
  echo "render_golden: manifest contains no cases" >&2
  exit 2
fi
echo "render_golden: $pass passed, $fail failed"
[ "$fail" = 0 ]
