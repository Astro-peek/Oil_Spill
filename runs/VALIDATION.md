# Validation record

- 42 regression checks passed across test_ai.py (11), test_drift.py (10), test_ais.py (7), test_ais_integration.py (5), test_geometry.py (7), and test_spill.py (2).
- Headless pipeline smoke: real Part III Oil/00023.tif with explicit synthetic forcing, synthetic AIS and demonstration timestamp; all processing stages completed.
- Trained-verifier smoke: real Part III Oil/00023.tif through the optional classifier and artifact exporter; completed successfully.
- Full labelled image benchmark: 450 scenes; see evaluation_full/report.json, samples.json and manifest.json.
- Fixed-seed subset benchmark: 45 scenes; see evaluation_sample.
- Proposed API schemas were checked with jsonschema; a valid request was accepted and invalid particle count rejected. This is not an HTTP integration test; the HTTP server is only planned.
- Modified Python modules compile successfully.

Synthetic test fixtures verify implementation and numerical properties. They do not establish real-world physical drift or vessel attribution accuracy.
