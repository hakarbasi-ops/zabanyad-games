#!/usr/bin/env bash
# Builds dist/zabanyad-games-<VERSION>.zip (single top folder zabanyad-games/, wheels included).
set -euo pipefail
cd "$(dirname "$0")/.."
VER="$(cat app/VERSION)"
OUT="dist/zabanyad-games-$VER.zip"
TMP="$(mktemp -d)"
mkdir -p dist "$TMP/zabanyad-games"
git archive HEAD | tar -x -C "$TMP/zabanyad-games"
rm -rf "$TMP/zabanyad-games/tests" "$TMP/zabanyad-games/dist"
(cd "$TMP" && zip -qr - zabanyad-games) > "$OUT"
rm -rf "$TMP"
echo "$OUT ($(du -h "$OUT" | cut -f1))"
