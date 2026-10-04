#!/usr/bin/env bash
# Needs ~/.kaggle/kaggle.json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KG="$ROOT/.venv/bin/kaggle"
cd "$ROOT/data"

dl() { echo ">>> $1"; "$KG" datasets download -d "$1" -p "$2" --unzip; }

dl bitsandlayers/sar-oil-spill-segmentation-dataset-sos spill_sos
dl kailaspsudheer/sarscope-unveiling-the-maritime-landscape ship_sarscope
dl harikrishnacs/sentinel-1-sar-oil-spill-detection-dataset spill_csiro
echo "=== DONE ==="
