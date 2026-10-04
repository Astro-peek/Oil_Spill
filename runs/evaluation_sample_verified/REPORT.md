# Scene verifier evaluation

| Metric | Baseline | With verifier |
|---|---:|---:|
| Scene accuracy | 0.8000 | 0.8444 |
| Scene precision | 0.6250 | 0.7857 |
| Scene recall | 1.0000 | 0.7333 |
| Scene specificity | 0.7000 | 0.9000 |
| All-scene pixel iou | 0.3373 | 0.3387 |
| All-scene pixel dice | 0.5044 | 0.5060 |

Part III test imagery; fixed threshold, no fitting or calibration on test samples. Scene detection uses area filtering; pixel metrics use the raw thresholded mask. Empty positive denominators are null. Scene verifier threshold fixed on Part I/II validation. Gate metrics derived exactly from unchanged baseline confusion counts.

See samples.json for every accepted/rejected scene. Scores are not calibrated probabilities.
