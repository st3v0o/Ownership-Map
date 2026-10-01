#!/usr/bin/env bash
# Turn build/parcels.ndjson into site/data/parcels.pmtiles (vector tiles).
# Zoomed out (z10-13) tiles carry only what the colors, chart filters and
# owner outlines need; zoomed in (z14-16) tiles carry every attribute for popups.
set -euo pipefail
IN=${1:-build/parcels.ndjson}
OUT=${2:-site/data/parcels.pmtiles}
TMP=$(mktemp -d)
mkdir -p "$(dirname "$OUT")"

tippecanoe -q -P -o "$TMP/low.pmtiles" -l parcels -Z10 -z13 \
  -y c -y id -y k -y g -y v -y u -y w --no-tile-size-limit --no-feature-limit --no-tiny-polygon-reduction --simplification=4 "$IN"
tippecanoe -q -P -o "$TMP/high.pmtiles" -l parcels -Z14 -z16 \
  --no-tile-size-limit --no-feature-limit "$IN"
tile-join -q -f -n "Richmond residential parcels" -o "$OUT" --no-tile-size-limit "$TMP/low.pmtiles" "$TMP/high.pmtiles"
rm -rf "$TMP"
ls -lh "$OUT"
