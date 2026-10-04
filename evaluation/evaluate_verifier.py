"""Evaluate a fixed verifier on the exact manifest of a completed segmentation benchmark.

No threshold fitting occurs here. Accepted scenes retain baseline predictions;
rejected scenes have an all-negative mask, so pixel confusion counts can be derived
exactly from the baseline counts without rerunning segmentation.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import torch
from oilspill.metrics import sha256, metrics
from oilspill.predict_scene import load_model
from oilspill.scene_verifier import SceneVerifier


def evaluate(baseline, verifier_path, out):
    baseline, out = Path(baseline), Path(out)
    report = json.loads((baseline/'report.json').read_text())
    rows = json.loads((baseline/'samples.json').read_text())
    if report['checkpoint_sha256'] != sha256(report['checkpoint']):
        raise ValueError('Baseline checkpoint changed')
    model_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    torch.set_num_threads(4)
    model = load_model(report['checkpoint'], model_device)
    verifier = SceneVerifier(verifier_path, report['checkpoint'])
    out.mkdir(parents=True, exist_ok=True)
    totals = dict.fromkeys(['tp', 'fp', 'fn', 'tn'], 0)
    scene = dict(totals)
    by_class, new_rows = {}, []
    for i, row in enumerate(rows):
        path = row['image']
        if sha256(path) != row['image_sha256']:
            raise ValueError(f'Baseline image changed: {path}')
        v = verifier.predict(model, path, model_device)
        c = {k: row['pixel_metrics'][k] for k in totals}
        if not v['accepted']:
            c = {'tp': 0, 'fp': 0, 'fn': c['tp']+c['fn'], 'tn': c['tn']+c['fp']}
        detected = row['detected'] and v['accepted']
        actual = row['category'] == 'Oil'
        key = ('tp' if detected else 'fn') if actual else ('fp' if detected else 'tn')
        scene[key] += 1
        category = by_class.setdefault(row['category'], {'scenes': 0, 'flagged': 0, 'pixels': dict.fromkeys(totals, 0)})
        category['scenes'] += 1
        category['flagged'] += int(detected)
        for k in totals:
            totals[k] += c[k]
            category['pixels'][k] += c[k]
        new_rows.append({**row, 'detected': detected, 'pixel_metrics': metrics(c),
                         'total_area_km2': row['total_area_km2'] if v['accepted'] else 0,
                         'scene_verification': v, 'baseline_detected': row['detected']})
        if (i+1) % 15 == 0:
            print(f'verified {i+1}/{len(rows)}', flush=True)
        (out/'samples.json').write_text(json.dumps(new_rows, indent=2, allow_nan=False))
    for cl in by_class.values():
        cl['pixel_metrics'] = metrics(cl.pop('pixels'))
        cl['flag_rate'] = cl['flagged']/cl['scenes']
    result = {**report, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'verifier': str(verifier_path), 'verifier_sha256': sha256(verifier_path),
              'baseline_report': str(baseline/'report.json'), 'scene_metrics': metrics(scene),
              'pixel_metrics': metrics(totals), 'by_class': by_class,
              'protocol': report['protocol']+' Scene verifier threshold fixed on Part I/II validation. Gate metrics derived exactly from unchanged baseline confusion counts.'}
    (out/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    lines = ['# Scene verifier evaluation', '', '| Metric | Baseline | With verifier |', '|---|---:|---:|']
    for key in ['accuracy', 'precision', 'recall', 'specificity']:
        lines.append(f"| Scene {key} | {report['scene_metrics'][key]:.4f} | {result['scene_metrics'][key]:.4f} |")
    for key in ['iou', 'dice']:
        lines.append(f"| All-scene pixel {key} | {report['pixel_metrics'][key]:.4f} | {result['pixel_metrics'][key]:.4f} |")
    lines += ['', result['protocol'], '', 'See samples.json for every accepted/rejected scene. Scores are not calibrated probabilities.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result['scene_metrics'], indent=2))
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', default='runs/evaluation_full')
    ap.add_argument('--verifier', default='runs/scene_verifier/verifier.json')
    ap.add_argument('--out', default='runs/evaluation_verified')
    a = ap.parse_args()
    evaluate(a.baseline, a.verifier, a.out)
