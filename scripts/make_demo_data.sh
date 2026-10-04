#!/usr/bin/env bash
# Copy the minimal demo scenes off the HDD into demo_data/ so the demo runs unmounted.
# Three Part III scenes: one oil (true positive), one look-alike and one clean
# (the false-alarm behaviour that is the honest half of the story).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/data/zenodo_part3"
DST="$ROOT/demo_data"

[ -d "$SRC/Images" ] || { echo "HDD not mounted: $SRC missing"; exit 1; }

# 00023 is the oil scene already used in runs/VALIDATION.md, so the demo matches the record.
copy() { # <class> <stem>
  mkdir -p "$DST/Images/$1" "$DST/Mask/$1"
  cp -v "$SRC/Images/$1/$2.tif" "$DST/Images/$1/"
  cp -v "$SRC/Mask/$1/$2"_segmentation.tif "$DST/Mask/$1/"
}
copy Oil 00023
copy Lookalike 00000
copy "No oil" 00000

du -sh "$DST"
echo "Demo: .venv/bin/python -m oilspill.ai_pipeline \\"
echo "  --image demo_data/Images/Oil/00023.tif --out runs/demo --demo \\"
echo "  --ais runs/smoke_inputs/synthetic_ais.csv --when 2026-06-12T06:00:00Z"
