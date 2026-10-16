#!/usr/bin/env bash
# Save the lake as a release asset. GitHub allows 2 GB per asset; prune.sh keeps us far below that.
set -euo pipefail
LAKE="${NIGHTFALL_LAKE:-lake}"
TMP="$(mktemp -d)"
tar --use-compress-program="zstd -19 -T0" -cf "$TMP/lake.tar.zst" -C "$LAKE" .
SIZE=$(stat -c %s "$TMP/lake.tar.zst")
if [ "$SIZE" -gt 1800000000 ]; then
  echo "lake is $SIZE bytes, close to GitHub's 2 GB asset limit; run \`nightfall prune\` or archive old raw data" >&2
  exit 1
fi
gh release view lake-latest >/dev/null 2>&1 || gh release create lake-latest --title "Data lake (rolling)" \
  --notes "Raw and staged data restored by the pipeline each run. Not a software release." --prerelease
gh release upload lake-latest "$TMP/lake.tar.zst" --clobber
echo "pushed lake: $(numfmt --to=iec "$SIZE")"
rm -rf "$TMP"
