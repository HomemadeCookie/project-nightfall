#!/usr/bin/env bash
# Restore the data lake from the rolling GitHub Release "lake-latest". A missing release means a fresh start.
set -euo pipefail
LAKE="${NIGHTFALL_LAKE:-lake}"
TMP="$(mktemp -d)"
if gh release download lake-latest --pattern lake.tar.zst --dir "$TMP" 2>/dev/null; then
  mkdir -p "$LAKE"
  tar --use-compress-program=unzstd -xf "$TMP/lake.tar.zst" -C "$LAKE"
  echo "restored lake: $(du -sh "$LAKE" | cut -f1)"
else
  echo "no lake-latest release yet; starting empty"
  mkdir -p "$LAKE"
fi
rm -rf "$TMP"
