#!/usr/bin/env bash
# Download the trained model and the demo scenes from the GitHub Release, so a
# fresh clone can run the pipeline without the external HDD. Safe to re-run:
# anything already present is left alone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${OILSPILL_REPO:-DorianAarno/sih_oil_spill}"
TAG="${OILSPILL_TAG:-v1.0}"
BASE="https://github.com/$REPO/releases/download/$TAG"
cd "$ROOT"

# The repo is private, so an unauthenticated curl gets a 404. Use the gh CLI
# when it is logged in; fall back to curl, which is all a public repo needs.
get() { # <asset-name> <destination>
  if [ -f "$2" ]; then echo "already have $2"; return; fi
  echo "downloading $1 -> $2"
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    gh release download "$TAG" --repo "$REPO" --pattern "$1" --output "$2.part" --clobber
  else
    curl -fL --progress-bar -o "$2.part" "$BASE/$1"
  fi
  mv "$2.part" "$2"
}

mkdir -p runs
get spill_unet_tiles.pt runs/spill_unet_tiles.pt

# models.json is the checksum record; a truncated or tampered download fails here.
want=$(python3 -c "import json;print(json.load(open('models.json'))['models'][0]['sha256'])")
echo "$want  runs/spill_unet_tiles.pt" | sha256sum -c -

if [ ! -d demo_data ]; then
  get demo_data.tar.gz demo_data.tar.gz
  tar xzf demo_data.tar.gz && rm -f demo_data.tar.gz
fi

echo
echo "Ready. Try:"
echo "  .venv/bin/python -m oilspill.ai_pipeline \\"
echo "    --image demo_data/Images/Oil/00023.tif --out runs/demo --demo \\"
echo "    --ais runs/smoke_inputs/synthetic_ais.csv --when 2026-06-12T06:00:00Z"
