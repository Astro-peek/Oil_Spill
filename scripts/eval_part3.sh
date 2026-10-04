#!/usr/bin/env bash
# The number that matters: does the model fire on look-alikes and clean water?
# Part III is a genuinely held-out test — different basin (E Med / Red Sea) from training (North Sea).
set -u
P=/home/aarno/dev/personal/sih/oil_spill
CKPT="${1:-runs/spill_unet_tiles.pt}"; THR="${2:-0.5}"; MINA="${3:-0.05}"
cd "$P"
D=data/zenodo_part3
for c in Oil Lookalike "No oil"; do
  extra=""; [ "$c" = "Oil" ] && extra="--truth $D/Mask/Oil"
  .venv/bin/python -m oilspill.predict_scene --ckpt "$CKPT" --channels dual \
    --images "$D/Images/$c/*.tif" --label "$c" --thr "$THR" --min-area-km2 "$MINA" \
    --out "runs/p3_${c// /_}.json" $extra 2>&1 | grep -E "^\["
done
