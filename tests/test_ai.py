"""Headless AI regression tests: inference boundaries, forcing coverage and output contracts."""
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
import torch
import xarray as xr

from oilspill.ais import interp_track
from oilspill.drift import advect, UniformField, hindcast_origin, seed_from_polygon
from oilspill.metrics import binary_counts, metrics
from oilspill.ocean_field import NetCDFVectorField, CoverageError
from oilspill.predict_scene import predict, run_scene
from oilspill.ai_pipeline import AnalysisConfig, OilSpillAI, drift_slick, rank_origins


class ConstantModel(torch.nn.Module):
    def forward(self, x):
        return torch.full((len(x), 1, x.shape[2], x.shape[3]), 2., device=x.device)


def expect_error(fn, kind=ValueError):
    try:
        fn()
    except kind:
        return
    raise AssertionError(f'Expected {kind.__name__}')


def raster(path, shape=(65, 49), crs='EPSG:32636', nodata=False):
    raw = np.ones((2, *shape), dtype='float32')
    raw[0] *= -15
    raw[1] *= -25
    if nodata:
        raw[:, :3] = -9999
    with rasterio.open(path, 'w', driver='GTiff', height=shape[0], width=shape[1], count=2,
                       dtype='float32', crs=crs, transform=from_origin(500000, 3900000, 10, 10),
                       nodata=-9999) as dst:
        dst.write(raw)


def test_tiling_small_and_irregular():
    for h, w in [(5, 7), (256, 301), (289, 37)]:
        p = predict(ConstantModel(), np.zeros((h, w, 3), np.uint8), torch.device('cpu'), bs=2)
        assert p.shape == (h, w)
        assert np.allclose(p, 1/(1+np.exp(-2)))
    expect_error(lambda: predict(ConstantModel(), np.zeros((32, 32, 3)), torch.device('cpu'), stride=300))


def test_nodata_is_not_detected():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)/'scene.tif'
        raster(path, nodata=True)
        p = run_scene(ConstantModel(), path, torch.device('cpu'))
        assert (p[:3] == 0).all()
        assert (p[3:] > .5).all()


def test_metrics_include_negative_false_positives():
    c = binary_counts([1, 1, 0, 0], [1, 0, 1, 0])
    m = metrics(c)
    assert m['accuracy'] == .5 and m['iou'] == 1/3 and m['dice'] == .5
    assert metrics(binary_counts([0], [0]))['iou'] is None
    expect_error(lambda: binary_counts([0], [0, 0]))


def test_exact_drift_duration_and_zero():
    t, L, A = advect([33.], [35.], UniformField(.1, 0), hours=.1, dt_s=900)
    assert t[-1] == 360
    t, L, A = advect([33.], [35.], UniformField(.1, 0), hours=0)
    assert len(t) == 1 and L[0, 0] == 33
    t, _, _ = advect([33.], [35.], UniformField(.1, 0), hours=-.3, dt_s=900)
    assert t[-1] == -1080
    expect_error(lambda: advect([33.], [35.], UniformField(0, 0), hours=1, dt_s=0))


def test_grid_interpolation_and_coverage():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)/'currents.nc'
        vals = np.ones((3, 2, 2))*.2
        ds = xr.Dataset({'uo': (('time', 'latitude', 'longitude'), vals, {'units': 'm s-1'}),
                         'vo': (('time', 'latitude', 'longitude'), vals*.5, {'units': 'm s-1'})},
                        coords={'time': pd.date_range('2026-01-01', periods=3, freq='h'),
                                'latitude': [36., 34.], 'longitude': [32., 34.]})
        ds.to_netcdf(p)
        field = NetCDFVectorField(p, '2026-01-01T05:30:00+05:30')
        u, v = field([33], [35], 1800)
        assert np.allclose(u, .2) and np.allclose(v, .1)
        expect_error(lambda: field([33], [35], -1), CoverageError)
        expect_error(lambda: field([40], [35], 1800), CoverageError)
        ds['uo'][0, 0, 0] = np.nan
        ds.to_netcdf(p)
        expect_error(lambda: NetCDFVectorField(p, '2026-01-01')([33], [35], 100), CoverageError)


def test_long_gap_not_interpolated():
    g = pd.DataFrame({'BaseDateTime': pd.to_datetime(['2026-01-01', '2026-01-02']),
                      'LON': [0, 1], 'LAT': [0, 1], 'COG': [0, 0], 'SOG': [10, 10]})
    gi = interp_track(g, pd.Timestamp('2026-01-01 10:00'), pd.Timestamp('2026-01-01 11:00'))
    assert gi.empty


def test_headless_output_and_no_detection():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)/'scene.tif'
        raster(p, nodata=True)
        ai = OilSpillAI.__new__(OilSpillAI)
        ai.config = AnalysisConfig(min_area_km2=.01)
        ai.model, ai.device, ai.verifier = ConstantModel(), torch.device('cpu'), None
        ai.checkpoint_sha256 = 'test-double'
        result = ai.analyze(p, Path(d)/'result')
        assert result['summary']['detected']
        assert result['incidents'][0]['drift_status'] == 'missing_currents'
        with rasterio.open(Path(d)/'result/mask.tif') as src:
            assert src.crs.to_epsg() == 32636 and src.nodata == 255
            assert (src.read(1)[:3] == 255).all()
        ai.config = AnalysisConfig(min_area_km2=10)
        result = ai.analyze(p, Path(d)/'empty')
        assert not result['summary']['detected'] and result['incidents'] == []
        with rasterio.open(Path(d)/'empty/mask.tif') as src:
            assert (src.read(1)[3:] == 0).all()


def test_unresolved_origin_retains_time_hypotheses():
    slick = {'geometry': {'type': 'Polygon', 'coordinates': [[[33, 35], [33.01, 35],
                                                            [33.01, 35.01], [33, 35.01], [33, 35]]]}}
    c = AnalysisConfig(particles=20, ensemble_members=2, forecast_hours=1, hindcast_hours=2)
    r = drift_slick(slick, UniformField(.1, .1), '2026-01-01', c, 0)
    assert not r['timing_resolved_all_members']
    assert {h['hours_back'] for h in r['origins']} >= {0, 2}
    assert max(f['properties'].get('hours_ahead', 0) for f in r['features']) == 1


def test_grid_linear_time_space_and_surface_selection():
    with tempfile.TemporaryDirectory() as d:
        t = np.array([-3600., 0., 3600.])
        lat, lon = np.array([34., 36.]), np.array([32., 34.])
        surface = 1e-5*t[:, None, None] + .1*lat[None, :, None] + .2*lon[None, None, :]
        values = np.stack([surface, surface+100], axis=1)
        ds = xr.Dataset({'uo': (('time', 'depth', 'lat', 'lon'), values, {'units': 'm/s'}),
                         'vo': (('time', 'depth', 'lat', 'lon'), values*0, {'units': 'm/s'})},
                        coords={'time': pd.date_range('2026-01-01', periods=3, freq='h'),
                                'depth': [0, 10], 'lat': lat, 'lon': lon})
        path = Path(d)/'linear.nc'
        ds.to_netcdf(path)
        field = NetCDFVectorField(path, '2026-01-01T01:00Z')
        u, v = field([33.], [35.], 1800)
        assert np.allclose(u, [10.118]) and np.allclose(v, 0)


def test_verifier_rejection_exports_empty_decision():
    class Reject:
        def predict(self, *args):
            return {'score': .1, 'threshold': .5, 'accepted': False, 'calibrated': False}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)/'scene.tif'
        raster(path)
        ai = OilSpillAI.__new__(OilSpillAI)
        ai.config = AnalysisConfig(min_area_km2=.01)
        ai.model, ai.device, ai.verifier = ConstantModel(), torch.device('cpu'), Reject()
        ai.checkpoint_sha256 = 'test-double'
        result = ai.analyze(path, Path(d)/'rejected')
        assert result['summary']['n_slicks'] == 0 and not result['scene_verification']['accepted']
        with rasterio.open(Path(d)/'rejected/probability.tif') as src:
            assert src.read(1).max() > .5  # original scores retained for review
        with rasterio.open(Path(d)/'rejected/mask.tif') as src:
            assert src.read(1).max() == 0


def test_classifier_calibration_has_numeric_margin():
    from oilspill.scene_verifier import calibrate_threshold
    scores = np.array([.9, .6, .4, .1])
    labels = np.array([1, 1, 0, 0])
    threshold = calibrate_threshold(scores, labels, target_recall=1)
    assert .4 < threshold < .6
    assert np.array_equal(scores+1e-10 >= threshold, labels.astype(bool))
    assert np.array_equal(scores-1e-10 >= threshold, labels.astype(bool))


if __name__ == '__main__':
    torch.set_num_threads(2)
    for name, fn in sorted(list(globals().items())):
        if name.startswith('test_'):
            fn()
            print('ok', name)
