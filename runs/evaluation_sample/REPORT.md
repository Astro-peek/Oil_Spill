# AI image evaluation

Checkpoint: `runs/spill_unet_tiles.pt`

Scenes: 45; seed: 20260911; threshold: 0.5; minimum slick area: 0.05 km².

| Metric | Value |
|---|---:|
| Scene tp | 15.0000 |
| Scene fp | 9.0000 |
| Scene fn | 0.0000 |
| Scene tn | 21.0000 |
| Scene accuracy | 0.8000 |
| Scene precision | 0.6250 |
| Scene recall | 1.0000 |
| Scene specificity | 0.7000 |
| Scene iou | 0.6250 |
| Scene dice | 0.7692 |

| All-category pixel metric | Value |
|---|---:|
| iou | 0.3373 |
| dice | 0.5044 |
| precision | 0.3600 |
| recall | 0.8424 |
| accuracy | 0.9350 |

| Category | Scenes | Flagged | Pixel IoU |
|---|---:|---:|---:|
| Oil | 15 | 15 | 0.8075505028824063 |
| Lookalike | 15 | 7 | 0.0 |
| No oil | 15 | 2 | 0.0 |

Part III test imagery; fixed threshold, no fitting or calibration on test samples. Scene detection uses area filtering; pixel metrics use the raw thresholded mask. Empty positive denominators are null.

SAR detection only. Does not measure real-world drift or vessel attribution accuracy.

Sample panels: SAR input, labelled mask, predicted mask, and TP/FP/FN overlay.

Dataset source: https://zenodo.org/records/13761290. See manifest.json and samples.json for exact inputs, hashes and per-image results.
