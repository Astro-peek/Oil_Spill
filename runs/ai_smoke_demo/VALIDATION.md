# Integration smoke test

Input: real labelled Part III Oil/00023.tif. Segmentation used the trained dual-pol checkpoint.
Drift used a uniform synthetic field; AIS used generated traffic. The 2026 timestamp is synthetic and does not claim to be the scene acquisition time.

Result: detection, geometry, drift and AIS attribution stages executed successfully. One slick, ten origin/time hypotheses and four vessel candidates were returned.

This checks execution and output compatibility. It does not measure physical drift or attribution accuracy on a real incident.
