"""GUI helpers: result text covers every stage status, and the preview paints oil red."""
import json
import tempfile
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from gui import format_result, preview_image


def test_format_full_and_empty_results():
    r = json.loads(Path('runs/ai_smoke_demo/analysis.json').read_text())
    text = format_result(r, 'out')
    assert 'Oil detected: YES' in text and 'SUSPECT_A' in text and 'km²' in text
    inc = r['incidents'][0]
    inc.update(drift_status='missing_currents')
    assert 'drift       not run (missing_currents)' in format_result(r, 'out')
    r['summary'].update(detected=False, n_slicks=0)
    r['incidents'] = []
    assert 'Oil detected: no' in format_result(r, 'out')


def test_preview_marks_oil_red():
    with tempfile.TemporaryDirectory() as d:
        image, mask = Path(d)/'scene.tif', Path(d)/'mask.tif'
        profile = dict(driver='GTiff', height=40, width=40, crs='EPSG:4326', transform=from_origin(0, 1, 1e-3, 1e-3))
        with rasterio.open(image, 'w', count=2, dtype='float32', **profile) as dst:
            dst.write(np.random.default_rng(0).normal(-15, 2, (2, 40, 40)).astype('float32'))
        m = np.zeros((40, 40), 'uint8')
        m[10:20] = 1
        with rasterio.open(mask, 'w', count=1, dtype='uint8', **profile) as dst:
            dst.write(m, 1)
        rgb = np.asarray(preview_image(image, mask, size=40))
        assert rgb.shape == (40, 40, 3)
        assert (rgb[10:20, :, 0] > rgb[10:20, :, 1]).all()          # oil rows tinted red
        assert (rgb[25:, :, 0] == rgb[25:, :, 1]).all()             # water stays grey


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
