# Final AI accuracy report

Fresh inference on 450 labelled Part III SAR images (150 per category). The original segmentation weights were retained. A new optional scene classifier was trained on 1,658 Part I/II scenes, validated on 226 scenes, with one unreadable TIFF excluded.

| Metric | Default segmenter | With optional verifier |
|---|---:|---:|
| Scene accuracy | 78.44% | 87.11% |
| Scene precision | 61.00% | 85.38% |
| Oil-scene recall | 98.00% | 74.00% |
| Negative-scene specificity | 68.67% | 93.67% |
| Pixel IoU, all categories | 37.88% | 36.69% |
| Pixel Dice, all categories | 54.95% | 53.68% |

| Category | Images | Default flagged | Verifier flagged |
|---|---:|---:|---:|
| Oil | 150 | 147 | 111 |
| Lookalike | 150 | 77 | 11 |
| No oil | 150 | 17 | 8 |

## Decision

Keep the segmenter as the default because it detects 147/150 oil scenes. The optional verifier reduces false alarms but detects only 111/150 oil scenes. Higher scene accuracy does not compensate automatically for that recall loss; choose the mode according to an explicitly accepted operating requirement.

Oil-only pixel IoU is 73.24% for the default. All-category IoU above includes false-positive pixels in negative scenes. Overall background-dominated pixel accuracy is not the headline metric.

## Reproduction and artifacts

- Baseline: [full report](../runs/evaluation_full/REPORT.md), [machine-readable metrics](../runs/evaluation_full/report.json), [per-scene results](../runs/evaluation_full/samples.json).
- Current verifier: [comparison report](../runs/evaluation_verified_final/REPORT.md), [metrics](../runs/evaluation_verified_final/report.json).
- Example real image, truth and prediction: [oil sample](../runs/evaluation_sample/Oil_00003.png).
- Example classifier failure: [missed real oil scene](../runs/evaluation_sample_verified/rejected_Oil_00022.png). The fixed-seed sample decisions remained unchanged after the serialization calibration fix.
- Model: [verifier artifact](../runs/scene_verifier/verifier.json), [train/validation split](../runs/scene_verifier/split.json), [excluded input](../runs/scene_verifier/excluded.json).

Threshold calibration used only Part I/II validation. The final runtime boundary is 0.14807636, set between adjacent validation scores to avoid floating-point equality at the boundary. Both comparisons use the same 450 images and fixed segmentation threshold 0.5/minimum area 0.05 km². Earlier comparison folders retain the initial verifier artifact; current results are in evaluation_verified_final.

## Limits

42 regression checks passed. A headless integration smoke test used real SAR imagery with explicitly synthetic forcing and AIS. Image benchmark scores do not measure real-world drift or vessel-attribution accuracy. EO is not trained. Event/geographic separation is not independently audited, and Part III was previously inspected in project diagnostics.

Dataset: [Zenodo Part III](https://zenodo.org/records/13761290).
