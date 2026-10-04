"""Web backend bridge: run the real AI on one scene and write the JSON shape frontend/script.js reads.

    python -m oilspill.web_bridge --out DIR --lat 19.07 --lon 72.88 [--image scene.tif] [--env '{...}']

No --image means a synthetic dual-pol scene with one slick is built at lat/lon (demo button).
Drift is forced by the UI sliders as uniform wind + current; AIS is synthetic (PS 26143 allows it).
"""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from oilspill.ai_pipeline import OilSpillAI, drift_slick, rank_origins
from oilspill.ais import haversine_km, synth_traffic
from oilspill.drift import DriftField, UniformField

KNOT = 0.514444


def synthetic_scene(path, lat, lon, n=1024, px_deg=9e-5, seed=0):
    """Speckled sea with one dark elongated slick at the centre, VV/VH in dB."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[:n, :n] - n / 2
    a = math.radians(35)
    oil = np.exp(-((x*math.cos(a) + y*math.sin(a)) / 260)**2 - ((-x*math.sin(a) + y*math.cos(a)) / 18)**2)
    speckle = 10 * np.log10(rng.gamma(4, 1/4, (2, n, n)))
    bands = np.stack([-9 - 12*oil + speckle[0], -20 - 8*oil + speckle[1]]).astype('float32')
    with rasterio.open(path, 'w', driver='GTiff', height=n, width=n, count=2, dtype='float32', crs='EPSG:4326',
                       transform=from_origin(lon - n/2*px_deg, lat + n/2*px_deg, px_deg, px_deg)) as dst:
        dst.write(bands)


def toward(speed, deg):
    """UI directions are 'toward' bearings (same convention as the old client-side drift)."""
    r = math.radians(deg)
    return UniformField(speed * math.sin(r), speed * math.cos(r))


def latlon(coords):
    return [[round(lat, 5), round(lon, 5)] for lon, lat in coords]


def to_frontend(result, out, env, when, ai):
    incidents = result['incidents']
    if not incidents:
        return {'detection': {'confidence': 0, 'areaKm2': 0, 'centroid': None, 'slickAgeHours': None,
                              'lookAlikeRisk': False, 'polygon': None, 'detected': False},
                'drift': {'trajectoryBack': [], 'trajectoryForward': [], 'origin': None, 'uncertaintyCone': []},
                'vessels': [], 'evidenceChain': [{'event_type': 'success', 'occurred_label': 'T-0h',
                                                  'title': 'No oil candidate found',
                                                  'description': 'The segmentation model found no slick above threshold.',
                                                  'source': 'U-Net (dual-pol SAR)'}]}
    inc = max(incidents, key=lambda i: i['geometry']['area_km2'])
    g = inc['geometry']
    with rasterio.open(out / 'probability.tif') as p, rasterio.open(out / 'mask.tif') as m:
        prob, mask = p.read(1), m.read(1) == 1
    confidence = round(float(prob[mask].mean()) * 100) if mask.any() else 0

    c = ai.config
    field = DriftField(current=toward(env['currentSpeed'], env['currentDir']),
                       wind=toward(env['windSpeed'] * KNOT, env['windDir']), windage=c.windage)
    drift = drift_slick(g, field, when, c, inc['slick_id'])
    origins = drift['origins']
    o_lat, o_lon = np.mean([o['lat'] for o in origins]), np.mean([o['lon'] for o in origins])
    radius = max(1.0, float(haversine_km(np.array([o['lon'] for o in origins]), np.array([o['lat'] for o in origins]),
                                         o_lon, o_lat).max()))
    hours_back = float(np.median([o['hours_back'] for o in origins]))
    envelopes = [f for f in drift['features'] if f['properties']['role'] == 'forecast_envelope']
    back = next(f for f in drift['features'] if f['properties']['role'] == 'hindcast_track')

    traffic = synth_traffic(o_lon, o_lat, when, culprit_offset_h=hours_back, culprit_course=g['orientation_deg'])
    ranked = rank_origins(traffic, origins, when, g['orientation_deg'], c)[:8]
    vessels = []
    for i, r in enumerate(ranked):
        t = traffic[traffic.MMSI == r['MMSI']].sort_values('BaseDateTime')
        t = t[abs((t.BaseDateTime - np.datetime64(r['cpa_time'][:-1])) / np.timedelta64(1, 'h')) <= 6]
        k = r['components']
        reasons = [s for s, ok in [(f"Closest approach {r['cpa_km']} km from origin", k['proximity'] > .3),
                                   (f"Passed {r['dt_hours']} h from estimated release time", k['timing'] > .3),
                                   (f"Course within {r['align_deg']}° of slick axis", k['alignment'] > .5),
                                   (f"Slowed by {r['speed_drop_kn']} kn in window", k['speed_drop'] > .3),
                                   ('AIS silent over estimated release', r['gap_covers_origin'])] if ok]
        lowering = [s for s, bad in [(f"Closest approach is {r['cpa_km']} km away", k['proximity'] <= .3),
                                     (f"Timing off by {r['dt_hours']} h", k['timing'] <= .3),
                                     (f"Course {r['align_deg']}° off slick axis", k['alignment'] <= .5)] if bad]
        vessels.append({'id': f'v{i+1}', 'mmsi': str(r['MMSI']), 'name': r['VesselName'], 'type': 'vessel',
                        'sog': f"{t.SOG.median():.1f} kts", 'cog': f"{r['cog_at_cpa']:03.0f}°",
                        'distKm': r['cpa_km'], 'score': round(r['score']),
                        'timeMatch': 'High' if r['dt_hours'] < 2 else 'Medium' if r['dt_hours'] < 6 else 'Low',
                        'trackPoints': [[round(a, 5), round(b, 5)] for a, b in zip(t.LAT, t.LON)][::3],
                        'reasons': reasons, 'lowering': lowering, 'anomaly': r['gap_covers_origin']})

    top = vessels[0] if vessels else None
    evidence = [
        {'event_type': 'success', 'occurred_label': 'T-0h', 'title': 'SAR oil candidate detected',
         'description': f"{g['area_km2']:.2f} km² slick, {g['major_axis_km']:.1f} × {g['minor_axis_km']:.2f} km, "
                        f"mean model probability {confidence}%.", 'source': 'U-Net (dual-pol SAR)'},
        {'event_type': 'success', 'occurred_label': f'T-{hours_back:.0f}h', 'title': 'Back-drift origin estimated',
         'description': f"Origin {o_lat:.4f}N {o_lon:.4f}E ± {radius:.1f} km from {c.ensemble_members}-member ensemble"
                        f"{'' if drift['timing_resolved_all_members'] else '; release time unresolved under uniform forcing'}.",
         'source': 'Lagrangian drift (slider forcing)'},
        *([{'event_type': 'warning', 'occurred_label': f"T-{hours_back:.0f}h", 'title': 'Top AIS candidate',
            'description': f"{top['name']} (MMSI {top['mmsi']}), closest {top['distKm']} km, score {top['score']}.",
            'source': 'Synthetic AIS'}] if top else []),
        {'event_type': 'warning', 'occurred_label': 'Note', 'title': 'Limitations',
         'description': ' '.join(result['limitations']), 'source': 'Pipeline'},
    ]
    return {'detection': {'confidence': confidence, 'areaKm2': round(result['summary']['total_area_km2'], 2),
                          'centroid': {'lat': g['centroid_lat'], 'lon': g['centroid_lon']},
                          'slickAgeHours': round(hours_back, 1), 'lookAlikeRisk': False,
                          'polygon': g['geometry'], 'detected': True},
            'drift': {'trajectoryBack': latlon(back['geometry']['coordinates']),
                      'trajectoryForward': [[round(float(a), 5), round(float(b), 5)] for b, a in
                                            [np.mean(f['geometry']['coordinates'][0], axis=0) for f in envelopes]],
                      'origin': {'lat': float(o_lat), 'lon': float(o_lon), 'radiusKm': round(radius, 1)},
                      'uncertaintyCone': latlon(envelopes[-1]['geometry']['coordinates'][0]) if envelopes else []},
            'vessels': vessels, 'evidenceChain': evidence}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    ap.add_argument('--lat', type=float, required=True)
    ap.add_argument('--lon', type=float, required=True)
    ap.add_argument('--image')
    ap.add_argument('--when', default='2026-09-13T06:42:00Z')
    ap.add_argument('--env', default='{"windSpeed":12,"windDir":45,"currentSpeed":0.8,"currentDir":30}')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    image = a.image
    if not image:
        image = out / 'synthetic_scene.tif'
        synthetic_scene(image, a.lat, a.lon)
    # GPU is usually held by other jobs; CPU inference is ~3 s per 1024² scene.
    ai = OilSpillAI(device=os.environ.get('OILSPILL_DEVICE', 'cpu'))
    result = ai.analyze(image, out / 'ai', a.when)
    web = to_frontend(result, out / 'ai', json.loads(a.env), a.when, ai)
    (out / 'web.json').write_text(json.dumps(web, allow_nan=False))


if __name__ == '__main__':
    main()
