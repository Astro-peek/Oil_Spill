# AI image evaluation

Checkpoint: `runs/spill_unet_tiles.pt`

Scenes: 450; seed: 20260911; threshold: 0.5; minimum slick area: 0.05 km².

| Metric | Value |
|---|---:|
| Scene tp | 147.0000 |
| Scene fp | 94.0000 |
| Scene fn | 3.0000 |
| Scene tn | 206.0000 |
| Scene accuracy | 0.7844 |
| Scene precision | 0.6100 |
| Scene recall | 0.9800 |
| Scene specificity | 0.6867 |
| Scene iou | 0.6025 |
| Scene dice | 0.7519 |

| All-category pixel metric | Value |
|---|---:|
| iou | 0.3788 |
| dice | 0.5495 |
| precision | 0.4163 |
| recall | 0.8082 |
| accuracy | 0.9561 |

| Category | Scenes | Flagged | Pixel IoU |
|---|---:|---:|---:|
| Oil | 150 | 147 | 0.7324263881885642 |
| Lookalike | 150 | 77 | 0.0 |
| No oil | 150 | 17 | 0.0 |

Part III test imagery; fixed threshold, no fitting or calibration on test samples. Scene detection uses area filtering; pixel metrics use the raw thresholded mask. Empty positive denominators are null.

SAR detection only. Does not measure real-world drift or vessel attribution accuracy.

Sample panels: SAR input, labelled mask, predicted mask, and TP/FP/FN overlay.

Dataset source: https://zenodo.org/records/13761290. See manifest.json and samples.json for exact inputs, hashes and per-image results.
