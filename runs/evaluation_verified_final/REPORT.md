# Scene verifier evaluation

| Metric | Baseline | With verifier |
|---|---:|---:|
| Scene accuracy | 0.7844 | 0.8711 |
| Scene precision | 0.6100 | 0.8538 |
| Scene recall | 0.9800 | 0.7400 |
| Scene specificity | 0.6867 | 0.9367 |
| All-scene pixel iou | 0.3788 | 0.3669 |
| All-scene pixel dice | 0.5495 | 0.5368 |

Part III test imagery; fixed threshold, no fitting or calibration on test samples. Scene detection uses area filtering; pixel metrics use the raw thresholded mask. Empty positive denominators are null. Scene verifier threshold fixed on Part I/II validation. Gate metrics derived exactly from unchanged baseline confusion counts.

See samples.json for every accepted/rejected scene. Scores are not calibrated probabilities.
