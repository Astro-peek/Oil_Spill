"""Web bridge: synthetic demo scene goes through the real model and comes out in the frontend's shape."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_demo_scene_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, '-m', 'oilspill.web_bridge', '--out', d, '--lat', '19.07', '--lon', '72.88'],
                       check=True)
        web = json.loads((Path(d) / 'web.json').read_text())
    det, drift = web['detection'], web['drift']
    assert det['detected'] and det['confidence'] > 50 and det['polygon']['type'] in {'Polygon', 'MultiPolygon'}
    assert abs(det['centroid']['lat'] - 19.07) < .01 and abs(det['centroid']['lon'] - 72.88) < .01
    assert drift['trajectoryBack'] and drift['trajectoryForward'] and drift['origin']['radiusKm'] >= 1
    assert web['vessels'][0]['name'] == 'SUSPECT_A' and web['vessels'][0]['trackPoints']
    assert [v['score'] for v in web['vessels']] == sorted((v['score'] for v in web['vessels']), reverse=True)


if __name__ == '__main__':
    test_demo_scene_end_to_end()
    print('web bridge ok')
