"""Headless AI pipeline: SAR inference, slick geometry, drift ensembles and AIS candidates."""
import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import torch
from shapely.geometry import MultiPoint, mapping

from oilspill.ais import load_ais, score_vessels, utc_time
from oilspill.drift import DriftField, UniformField, advect, hindcast_origin, seed_from_polygon
from oilspill.ocean_field import NetCDFVectorField
from oilspill.predict_scene import load_model, run_scene
from oilspill.spill_geometry import measure, geojson
from oilspill.metrics import sha256


@dataclass
class AnalysisConfig:
    checkpoint: str = 'runs/spill_unet_tiles.pt'
    channels: str = 'dual'
    threshold: float = .5
    min_area_km2: float = .05
    verifier: str | None = None
    particles: int = 200
    forecast_hours: float = 24
    hindcast_hours: float = 24
    dt_seconds: float = 900
    ensemble_members: int = 3
    velocity_std_m_s: float = .03
    diffusivity_m2_s: float = 5
    windage: float = .03
    radius_km: float = 60
    time_pad_hours: float = 6
    seed: int = 0

    def validate(self):
        if not 0 < self.threshold < 1 or self.channels not in {'dual', 'grey'}:
            raise ValueError('Invalid detection threshold or channel mode')
        if self.particles < 3 or not 1 <= self.ensemble_members <= 100:
            raise ValueError('Need >=3 particles and 1..100 ensemble members')
        values = [self.min_area_km2, self.velocity_std_m_s, self.diffusivity_m2_s, self.windage]
        if not all(np.isfinite(v) and v >= 0 for v in values):
            raise ValueError('Area, perturbation, diffusion and windage must be finite and nonnegative')
        values = [self.forecast_hours, self.hindcast_hours, self.dt_seconds, self.radius_km, self.time_pad_hours]
        if not all(np.isfinite(v) and v > 0 for v in values):
            raise ValueError('Durations, step, radius and time padding must be positive and finite')
        if self.verifier and self.channels != 'dual':
            raise ValueError('Scene verifier only supports dual-pol input')


class PerturbedField:
    def __init__(self, base, u, v):
        self.base, self.u, self.v = base, u, v

    def __call__(self, lon, lat, t):
        u, v = self.base(lon, lat, t)
        return u+self.u, v+self.v


def feature(geometry, **properties):
    return {'type': 'Feature', 'geometry': geometry, 'properties': properties}


def drift_slick(slick, field, acquired_at, config, slick_id):
    c = config
    lons, lats = seed_from_polygon(slick['geometry'], c.particles, c.seed)
    rng = np.random.default_rng(c.seed)
    paths, origins, diagnostics = [], [], []
    for member in range(c.ensemble_members):
        du, dv = rng.normal(0, c.velocity_std_m_s, 2) if member else (0., 0.)
        perturbed = PerturbedField(field, du, dv)
        ts, L, A = advect(lons, lats, perturbed, c.forecast_hours, dt_s=c.dt_seconds,
                          diffusivity=c.diffusivity_m2_s, seed=c.seed+member)
        paths.append((L, A))
        hc = hindcast_origin(lons, lats, perturbed, c.hindcast_hours, dt_s=c.dt_seconds)
        # Unresolved timing retains hypotheses over the searched track, not just its minimum.
        indexes = ([int(np.argmin(hc['minor_curve_m']))] if hc['time_resolved'] else
                   np.unique(np.linspace(0, len(hc['hours'])-1, 9).astype(int)).tolist())
        for i in indexes:
            origins.append({'lon': hc['track_lon'][i], 'lat': hc['track_lat'][i],
                            'hours_back': hc['hours'][i], 'member': member,
                            'timing_resolved': hc['time_resolved']})
        diagnostics.append({'member': member, 'velocity_offset_m_s': [float(du), float(dv)],
                            'hours_back': hc['hours_back'], 'time_resolved': hc['time_resolved'],
                            'contraction_ratio': hc['contraction_ratio'],
                            'hours': hc['hours'], 'minor_curve_m': hc['minor_curve_m'],
                            'track': list(map(list, zip(hc['track_lon'], hc['track_lat'])))})
    features = []
    for i in np.unique(np.linspace(1, len(ts)-1, min(8, len(ts)-1)).astype(int)):
        points = np.concatenate([np.column_stack((L[i], A[i])) for L, A in paths])
        hull = MultiPoint(points).convex_hull
        features.append(feature(mapping(hull), role='forecast_envelope', slick_id=slick_id,
                                hours_ahead=float(ts[i]/3600),
                                time=(utc_time(acquired_at)+pd.Timedelta(seconds=float(ts[i]))).isoformat()+'Z',
                                ensemble_members=c.ensemble_members, envelope_kind='particle convex hull; not a confidence contour'))
    for origin in origins:
        features.append(feature({'type': 'Point', 'coordinates': [origin['lon'], origin['lat']]},
                                role='origin_hypothesis', slick_id=slick_id, **origin))
    for d in diagnostics:
        features.append(feature({'type': 'LineString', 'coordinates': d['track']}, role='hindcast_track',
                                slick_id=slick_id, member=d['member']))
    return {'origins': origins, 'members': diagnostics,
            'timing_resolved_all_members': all(d['time_resolved'] for d in diagnostics),
            'uncertainty_method': 'constant velocity perturbations plus forward particle diffusion; sensitivity analysis, not calibrated uncertainty',
            'features': features}


def rank_origins(traffic, origins, acquired_at, orientation, config):
    matches = {}
    for h in origins:
        rows = score_vessels(traffic, h['lon'], h['lat'], acquired_at, h['hours_back'], orientation,
                             radius_km=config.radius_km, pad_h=config.time_pad_hours)
        for row in rows:
            matches.setdefault(row['MMSI'], []).append((row, h))
    ranked = []
    for mmsi, pairs in matches.items():
        best, origin = max(pairs, key=lambda p: p[0]['score'])
        scores = [p[0]['score'] for p in pairs]
        ranked.append({**best, 'score_min_across_hypotheses': min(scores) if len(pairs) == len(origins) else 0,
                       'score_mean_across_hypotheses': round(sum(scores)/len(origins), 2),
                       'matched_hypotheses': len(pairs), 'total_hypotheses': len(origins),
                       'best_origin_hypothesis': origin,
                       'interpretation': 'maximum compatibility over origin hypotheses; not probability of responsibility'})
    return sorted(ranked, key=lambda r: (-r['score'], r['MMSI']))


class OilSpillAI:
    def __init__(self, config=None, device=None):
        self.config = config or AnalysisConfig()
        self.config.validate()
        torch.set_num_threads(4)
        self.device = torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))
        self.model = load_model(self.config.checkpoint, self.device)
        self.checkpoint_sha256 = sha256(self.config.checkpoint)
        self.verifier = None
        if self.config.verifier:
            from oilspill.scene_verifier import SceneVerifier
            self.verifier = SceneVerifier(self.config.verifier, self.config.checkpoint)

    def analyze(self, image, out, acquired_at=None, currents=None, wind=None, ais=None, demo=False):
        c = self.config
        if demo and (currents or wind):
            raise ValueError('Demo forcing cannot be mixed with supplied current/wind files')
        if wind and not currents:
            raise ValueError('Wind-only forcing is unsupported; supply ocean currents')
        if (currents or demo) and not acquired_at:
            raise ValueError('Acquisition timestamp is required for drift')
        out = Path(out)
        # Dedicated empty output directories prevent accidental mixing of incident artifacts.
        if out.exists() and any(out.iterdir()):
            raise ValueError(f'Output directory must be empty: {out}')
        out.mkdir(parents=True, exist_ok=True)
        with rasterio.open(image) as src:
            if src.crs is None:
                raise ValueError('Georeferenced SAR imagery with a CRS is required')
            profile = src.profile.copy()
            valid = src.read_masks([1, 2] if c.channels == 'dual' else [1]).all(axis=0)
            raw = src.read([1, 2] if c.channels == 'dual' else [1])
            valid &= np.isfinite(raw).all(axis=0)
        probability = run_scene(self.model, image, self.device, c.channels)
        verification = self.verifier.predict(self.model, image, self.device) if self.verifier else None
        mask = (probability > c.threshold) & valid
        if verification and not verification['accepted']:
            mask[:] = False
        summary, slicks = measure(image, mask_array=mask, min_area_km2=c.min_area_km2)
        # The exported decision mask uses the same area filter as reported slicks.
        from rasterio.features import rasterize
        from rasterio.warp import transform_geom
        if slicks:
            shapes = [(transform_geom('EPSG:4326', profile['crs'], s['geometry']), 1) for s in slicks]
            mask = rasterize(shapes, out_shape=mask.shape, transform=profile['transform'], dtype='uint8').astype(bool)
        else:
            mask[:] = False
        profile.update(count=1, compress='deflate')
        for name, arr, dtype, nodata in [('probability.tif', np.where(valid, probability, -1), 'float32', -1),
                                         ('mask.tif', np.where(valid, mask, 255), 'uint8', 255)]:
            with rasterio.open(out/name, 'w', **{**profile, 'dtype': dtype, 'nodata': nodata}) as dst:
                dst.write(arr.astype(dtype), 1)
        observed = geojson(slicks)
        for i, f in enumerate(observed['features']):
            f['properties'].update(slick_id=i, role='observed')
        (out/'slicks.geojson').write_text(json.dumps(observed, allow_nan=False))
        field, forcing = None, {'kind': 'not_provided'}
        if currents:
            current_field = NetCDFVectorField(currents, acquired_at)
            wind_field = NetCDFVectorField(wind, acquired_at, 'u10', 'v10') if wind else None
            field = DriftField(current=current_field, wind=wind_field, windage=c.windage)
            forcing = {'kind': 'provided_netcdf', 'currents': current_field.provenance(),
                       'wind': wind_field.provenance() if wind_field else None}
            forcing['currents']['sha256'] = sha256(currents)
            if wind:
                forcing['wind']['sha256'] = sha256(wind)
        elif demo:
            field = DriftField(current=UniformField(.18, .09))
            forcing = {'kind': 'synthetic_demo', 'current_m_s': [.18, .09]}
        traffic = load_ais(ais) if ais else None
        incidents, drift_features = [], []
        for i, slick in enumerate(slicks):
            item = {'slick_id': i, 'geometry': slick, 'drift_status': 'missing_currents',
                    'attribution_status': 'missing_drift', 'vessels': []}
            if field is not None:
                result = drift_slick(slick, field, acquired_at, c, i)
                drift_features.extend(result.pop('features'))
                item.update(drift_status='completed', drift=result,
                            attribution_status='missing_ais' if traffic is None else 'completed')
                if traffic is not None:
                    item['vessels'] = rank_origins(traffic, result['origins'], acquired_at,
                                                  slick['orientation_deg'], c)
            incidents.append(item)
        (out/'drift.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': drift_features}, allow_nan=False))
        result = {'schema_version': '1.0', 'status': 'completed', 'summary': summary,
                  'acquired_at': utc_time(acquired_at).isoformat()+'Z' if acquired_at else None,
                  'config': asdict(c), 'scene_verification': verification,
                  'provenance': {'image': str(image), 'image_sha256': sha256(image),
                                 'checkpoint_sha256': self.checkpoint_sha256, 'forcing': forcing,
                                 'verifier_sha256': sha256(c.verifier) if c.verifier else None,
                                 'ais': {'file': str(ais), 'sha256': sha256(ais)} if ais else None},
                  'incidents': incidents,
                  'artifacts': {'probability': 'probability.tif', 'mask': 'mask.tif',
                                'slicks': 'slicks.geojson', 'drift': 'drift.geojson'},
                  'limitations': ['SAR candidate detection, not confirmed oil; EO models are not trained.',
                                  'Model age and origin are conditional on forcing, not observed release truth.',
                                  'AIS gaps over six hours are not interpolated; shorter gaps remain uncertain.',
                                  'Vessel scores are heuristic, uncalibrated investigation leads.']}
        (out/'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False))
        return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--when')
    ap.add_argument('--currents', help='NetCDF uo/vo surface currents in m/s')
    ap.add_argument('--wind', help='NetCDF u10/v10 wind in m/s')
    ap.add_argument('--ais', help='Recorded AIS CSV')
    ap.add_argument('--demo', action='store_true', help='Explicit synthetic forcing for integration checks')
    ap.add_argument('--ckpt', default='runs/spill_unet_tiles.pt')
    ap.add_argument('--verifier')
    ap.add_argument('--threshold', type=float, default=.5)
    ap.add_argument('--min-area-km2', type=float, default=.05)
    ap.add_argument('--forecast-hours', type=float, default=24)
    ap.add_argument('--hindcast-hours', type=float, default=24)
    ap.add_argument('--particles', type=int, default=200)
    ap.add_argument('--ensemble-members', type=int, default=3)
    a = ap.parse_args()
    c = AnalysisConfig(checkpoint=a.ckpt, verifier=a.verifier, threshold=a.threshold,
                       min_area_km2=a.min_area_km2, forecast_hours=a.forecast_hours,
                       hindcast_hours=a.hindcast_hours, particles=a.particles,
                       ensemble_members=a.ensemble_members)
    try:
        result = OilSpillAI(c).analyze(a.image, a.out, a.when, a.currents, a.wind, a.ais, a.demo)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    print(json.dumps(result['summary'], indent=2))
