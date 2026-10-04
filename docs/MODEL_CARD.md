# Oil spill AI model card

## Implemented components

| Component | Implementation | Evidence available |
|---|---|---|
| SAR detection | ResNet34 U-Net, overlapping 256-pixel windows, VV/VH/VV-VH inputs | Labelled Part III image evaluation |
| Lookalike rejection | Optional frozen-encoder scene classifier with SAR statistics | Part I/II scene validation and separate Part III testing |
| Slick geometry | Raster polygonization and local UTM metric measurements | Analytical geometry regression tests |
| Drift | RK2 particle advection, currents + windage, forward diffusion | Analytical displacement/coverage tests; synthetic integration run |
| Origin/age | Hindcast contraction minimum plus multiple hypotheses if unresolved | Synthetic field tests; no real release-time benchmark |
| Vessel ranking | Interpolated AIS proximity, time, orientation, gap and speed signals | Synthetic/regression tests; no real culprit-labelled benchmark |
| EO detection | Not trained | None |

## Segmentation artifact

`runs/spill_unet_tiles.pt`, SHA256 `b9a99e7b7b3c948cc729b283b712df28bc71c9e79e4b8916acb3903238644394`.
Architecture and channel count are fixed in the loader. `models.json` records available checkpoints and their input domains. Sigmoid values are model scores, not calibrated probabilities.

The existing model was trained using Part I oil and Part II lookalike scenes, with train/validation separated by `(tag, filename)`. Training log best validation IoU: 0.7490. This historical value is distinct from fresh testing. Dataset splits are scene-based; event/geographic overlap has not been independently audited. Part III had also been inspected in earlier project diagnostics, so this is a reproducible benchmark, not a claim of a never-inspected final release holdout.

The original and refined SOS models are retained, but their grayscale patch input distribution is different. The dual-pol scene model is the headless runner default. No pre-existing checkpoint was overwritten.

## Evaluation protocol

The primary test dataset is [Zenodo Part III](https://zenodo.org/records/13761290): 150 oil, 150 lookalike, and 150 oil-free SAR scenes, with two polarizations and labelled masks. Ground-truth masks inherit spatial indexing from their paired image; masks are not assumed georeferenced.

The threshold is 0.5 and minimum connected slick area is 0.05 km². Pixel IoU and Dice are calculated from aggregate confusion counts over valid pixels. Scene detection uses the minimum-area filter; pixel scores use the raw thresholded mask. Empty unions are undefined rather than counted as perfect matches.

`runs/evaluation_sample` records a fixed-seed balanced sample of 45 scenes. It found 15/15 oil detections, seven false detections among 15 lookalikes and two among 15 oil-free scenes. Scene accuracy: 80.0%; precision: 62.5%; recall: 100%. Oil-only pixel IoU: 80.76%; all-category pixel IoU: 33.73%. This difference demonstrates why negative scenes must be included.

Full-dataset and verifier results are recorded in their generated reports. Manifests, input/checkpoint hashes and per-scene counts make results reproducible. Sample panels show the image, truth, prediction and TP/FP/FN overlay; they are not hand-edited outputs.

## Scene classifier protocol

The optional classifier takes mean/std-pooled frozen encoder features and VV/VH/difference statistics from a reduced scene overview. It uses the exact original Part I/II scene split. Standardization fits training features only. The linear classifier checkpoint is selected by validation loss. The decision threshold is the validation boundary retaining at least 95% oil-scene recall, with a numerical margin.

Unreadable training TIFFs are excluded explicitly and listed in `runs/scene_verifier/excluded.json`. Excluded scenes are never assigned fabricated pixels or labels. The retained split is recorded in `split.json`; the model weights, normalizer, segmentation checksum, threshold and validation metrics are in `verifier.json`.

The verifier is optional and is not enabled by default. A scene-level rejection can suppress a small real spill. Its score is uncalibrated. Both baseline and verifier benchmarks must remain visible, including any test recall reduction.

## Limits and appropriate use

This is a headless research prototype for candidate detection and investigation support. It does not establish confirmed oil, a physical release age, or responsibility of a specific vessel. Real ocean fields can be supplied, but no matched incident forcing/release/vessel ground truth was available for an empirical end-to-end accuracy claim.

Synthetic demonstration forcing and AIS are marked as such. Particle envelopes are sensitivity outputs, not coverage-calibrated confidence intervals. Missing forcing coverage fails explicitly. Unknown origin time expands the hypotheses examined; vessel scores report compatibility across those hypotheses. Interpolation across AIS gaps is uncertain and stops for gaps over six hours.

Operational validation still needs event-separated imagery, coastal/lookalike stress tests, measured wind/current coverage, release trajectories/times and independently established vessel responsibility. EO capability would require its own model and labelled evaluation dataset.

## Fresh optional-classifier check

The verifier trained on 1,658 scenes and validated on 226; one unreadable Part II TIFF (`00389.tif`) was excluded. At its validation-selected threshold 0.14808, validation oil recall was 95.54% and negative specificity was 73.91%.

On the separate 45-scene sample, gating increased scene precision but reduced oil recall to 73.33% (11/15 oil scenes detected). This domain-transfer loss is why the classifier remains opt-in and the original segmenter remains the default. The test threshold was not retuned to hide missed oil scenes.

## Full 450-scene baseline benchmark

Fresh inference reproduced 147 true-positive oil scenes, 3 misses, 94 false-positive negative scenes and 206 true negatives. Scene accuracy is 78.44%, precision 61.00% and oil recall 98.00%. Of 150 lookalikes, 77 were flagged; of 150 oil-free scenes, 17 were flagged.

Oil-only pixel IoU is 73.24%. Across all three categories, pixel IoU is 37.88% and Dice is 54.95%. Overall pixel accuracy is 95.61%, but this is dominated by background pixels and must not be used alone to describe model quality.

The benchmark and nine deterministic sample panels are in `runs/evaluation_full`. This measured false-positive burden is an unresolved model limitation, not hidden by the complete software pipeline.

## Final serialized verifier benchmark

The final 450-scene verifier evaluation achieved scene accuracy 87.11%, precision 85.38% and oil recall 74.00%. It detected 111/150 oil scenes. See [ACCURACY_REPORT.md](ACCURACY_REPORT.md) for the complete comparison. The verifier remains optional.
