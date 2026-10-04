"""Reproducible labelled SAR evaluation with scene and pixel metrics and sample panels."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time

import numpy as np
import rasterio
import torch
from PIL import Image, ImageDraw
from oilspill.metrics import binary_counts, metrics, sha256
from oilspill.predict_scene import load_model, run_scene, to_uint8
from oilspill.spill_geometry import measure


def sample_panel(path, truth, pred, out, title):
    with rasterio.open(path) as src:
        grey = to_uint8(src.read(1).astype(np.float32))
    base = np.repeat(grey[..., None], 3, axis=2)
    overlay = base.copy()
    overlay[truth & pred] = [50, 210, 100]
    overlay[pred & ~truth] = [245, 90, 60]
    overlay[truth & ~pred] = [60, 150, 255]
    panel = Image.new('RGB', (1024, 300), '#101821')
    draw = ImageDraw.Draw(panel)
    draw.text((8, 5), title, fill='white')
    for i, (arr, label) in enumerate([(base, 'VV SAR'), (truth*255, 'Ground truth'),
                                     (pred*255, 'Prediction'), (overlay, 'Green TP / red FP / blue FN')]):
        tile = Image.fromarray(arr.astype(np.uint8)).convert('RGB').resize((256, 256))
        panel.paste(tile, (i*256, 40))
        draw.text((i*256+4, 23), label, fill='white')
    panel.save(out)


def evaluate(root, checkpoint, out, per_class=15, seed=20260911, threshold=.5,
             min_area=.05, channels='dual', batch_size=16):
    root, out = Path(root), Path(out)
    if not 0 < threshold < 1 or min_area < 0 or per_class < 0:
        raise ValueError('Invalid threshold, minimum area or sample count')
    selected = []
    rng = random.Random(seed)
    for category in ['Oil', 'Lookalike', 'No oil']:
        files = sorted((root/'Images'/category).glob('*.tif'))
        if not files:
            raise ValueError(f'No images for {category} in {root}')
        files = sorted(rng.sample(files, min(per_class, len(files)))) if per_class else files
        for image in files:
            truth = root/'Mask'/category/(image.stem+'_segmentation.tif')
            if not truth.exists():
                raise ValueError(f'Missing truth: {truth}')
            selected.append((category, image, truth))
    out.mkdir(parents=True, exist_ok=True)
    manifest = [{'category': c, 'image': str(i), 'truth': str(t)} for c, i, t in selected]
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    torch.set_num_threads(4)
    dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = load_model(checkpoint, dev)
    rows = []
    totals = {k: 0 for k in ('tp', 'fp', 'fn', 'tn')}
    scene_counts = dict(totals)
    by_class = {}
    for category, image, truth_path in selected:
        started = time.monotonic()
        prob = run_scene(model, image, dev, channels=channels, bs=batch_size)
        pred = prob > threshold
        with rasterio.open(truth_path) as src:
            truth = src.read(1) > 0
        with rasterio.open(image) as src:
            bands = src.read([1, 2] if channels == 'dual' else [1], masked=True).astype(np.float32).filled(np.nan)
            valid = np.isfinite(bands).all(axis=0)
        if category != 'Oil' and truth.any():
            raise ValueError(f'Negative category has nonempty oil mask: {truth_path}')
        counts = binary_counts(pred, truth, valid)
        summary, _ = measure(image, mask_array=pred, min_area_km2=min_area)
        actual = category == 'Oil'
        predicted = summary['detected']
        scene_key = ('tp' if predicted else 'fn') if actual else ('fp' if predicted else 'tn')
        scene_counts[scene_key] += 1
        for k in totals:
            totals[k] += counts[k]
        cl = by_class.setdefault(category, {'scenes': 0, 'flagged': 0, 'pixels': dict.fromkeys(totals, 0)})
        cl['scenes'] += 1
        cl['flagged'] += int(predicted)
        for k in totals:
            cl['pixels'][k] += counts[k]
        row = {'category': category, 'image': str(image), 'truth': str(truth_path),
               'image_sha256': sha256(image), 'truth_sha256': sha256(truth_path),
               'detected': predicted, 'total_area_km2': summary['total_area_km2'],
               'pixel_metrics': metrics(counts), 'seconds': round(time.monotonic()-started, 3)}
        if cl['scenes'] <= 3:
            name = f"{category.replace(' ', '_')}_{image.stem}.png"
            sample_panel(image, truth & valid, pred & valid, out/name,
                         f'{category} / {image.name} / flagged={predicted}')
            row['panel'] = name
        rows.append(row)
        (out/'samples.json').write_text(json.dumps(rows, indent=2, allow_nan=False))
        print(f"[{len(rows)}/{len(selected)}] {category}/{image.name}: flagged={predicted} IoU={row['pixel_metrics']['iou']} ({row['seconds']}s)", flush=True)
    for cl in by_class.values():
        cl['pixel_metrics'] = metrics(cl.pop('pixels'))
        cl['flag_rate'] = cl['flagged']/cl['scenes']
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'checkpoint': str(checkpoint), 'checkpoint_sha256': sha256(checkpoint),
              'device': str(dev), 'sample_seed': seed, 'n_scenes': len(rows),
              'threshold': threshold, 'min_area_km2': min_area, 'channels': channels,
              'scene_metrics': metrics(scene_counts), 'pixel_metrics': metrics(totals),
              'by_class': by_class,
              'protocol': 'Part III test imagery; fixed threshold, no fitting or calibration on test samples. Scene detection uses area filtering; pixel metrics use the raw thresholded mask. Empty positive denominators are null.',
              'scope': 'SAR detection only. Does not measure real-world drift or vessel attribution accuracy.'}
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    lines = ['# AI image evaluation', '', f"Checkpoint: `{checkpoint}`", '',
             f"Scenes: {len(rows)}; seed: {seed}; threshold: {threshold}; minimum slick area: {min_area} km².", '',
             '| Metric | Value |', '|---|---:|']
    for name, value in report['scene_metrics'].items():
        lines.append(f'| Scene {name} | {value:.4f} |' if value is not None else f'| Scene {name} | undefined |')
    for name in ['iou', 'dice', 'precision', 'recall', 'accuracy']:
        value = report['pixel_metrics'][name]
        lines.append(f'| All-category pixel {name} | {value:.4f} |' if value is not None else f'| All-category pixel {name} | undefined |')
    lines += ['', '| Category | Scenes | Flagged | Pixel IoU |', '|---|---:|---:|---:|']
    for c, r in by_class.items():
        lines.append(f"| {c} | {r['scenes']} | {r['flagged']} | {r['pixel_metrics']['iou']} |")
    lines += ['', report['protocol'], '', report['scope'], '',
              'Sample panels: SAR input, labelled mask, predicted mask, and TP/FP/FN overlay.', '',
              'Dataset source: https://zenodo.org/records/13761290. See manifest.json and samples.json for exact inputs, hashes and per-image results.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', default='data/zenodo_part3')
    ap.add_argument('--ckpt', default='runs/spill_unet_tiles.pt')
    ap.add_argument('--out', default='runs/evaluation')
    ap.add_argument('--per-class', type=int, default=15, help='0 evaluates all scenes')
    ap.add_argument('--seed', type=int, default=20260911)
    ap.add_argument('--threshold', type=float, default=.5)
    ap.add_argument('--min-area-km2', type=float, default=.05)
    ap.add_argument('--channels', choices=['dual', 'grey'], default='dual')
    ap.add_argument('--batch-size', type=int, default=16)
    a = ap.parse_args()
    evaluate(a.data, a.ckpt, a.out, a.per_class, a.seed, a.threshold, a.min_area_km2, a.channels, a.batch_size)
