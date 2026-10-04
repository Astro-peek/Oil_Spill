"""Frozen SAR encoder + learned scene classifier to reject oil lookalikes.

The classifier is fit on Part I/II only. It uses the segmenter's existing scene split,
so validation scenes remain unseen by both the encoder training and this classifier.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random

import numpy as np
import rasterio
import torch
import torch.nn.functional as F
from oilspill.predict_scene import load_model, to_uint8
from oilspill.metrics import sha256, binary_counts, metrics


@torch.inference_mode()
def extract_features(model, image, device, size=256):
    with rasterio.open(image) as src:
        if src.count < 2:
            raise ValueError('Scene verifier requires VV and VH')
        raw = src.read([1, 2], out_shape=(2, 512, 512), masked=True).astype(np.float32).filled(np.nan)
    channels = np.dstack([to_uint8(raw[0]), to_uint8(raw[1]), to_uint8(raw[0]-raw[1])])
    x = torch.from_numpy(channels.transpose(2, 0, 1).copy()).float()[None].to(device)/255
    x = F.interpolate(x, size=(size, size), mode='bilinear', align_corners=False)
    feats = model.encoder(x)
    last = feats[-1].float()
    pooled = torch.cat([last.mean((2, 3)), last.std((2, 3))], dim=1)[0].cpu().numpy()
    stats = []
    for band in [raw[0], raw[1], raw[0]-raw[1]]:
        finite = band[np.isfinite(band)]
        if not finite.size:
            raise ValueError(f'No valid pixels: {image}')
        stats.extend(np.percentile(finite, [5, 25, 50, 75, 95]).tolist())
        stats.extend([float(finite.mean()), float(finite.std())])
    return np.r_[pooled, stats].astype(np.float32)


def calibrate_threshold(scores, labels, target_recall=.95):
    """Choose a validation-only decision boundary with a margin between adjacent scores."""
    scores, labels = np.asarray(scores, float), np.asarray(labels, bool)
    if not labels.any():
        raise ValueError('Oil validation examples are required')
    candidates = sorted(set([0.0] + scores.tolist()))
    boundary = max(t for t in candidates if ((scores >= t) & labels).sum()/labels.sum() >= target_recall)
    below = scores[scores < boundary]
    return float((boundary + below.max()) / 2) if below.size else 0.0


class SceneVerifier:
    def __init__(self, path, checkpoint=None):
        self.config = json.loads(Path(path).read_text())
        if checkpoint and self.config['segmentation_sha256'] != sha256(checkpoint):
            raise ValueError('Scene verifier was trained with a different segmentation checkpoint')
        self.threshold = self.config['threshold']

    def predict(self, model, image, device):
        features = extract_features(model, image, device)
        c = self.config
        z = (features-np.array(c['mean']))/np.array(c['scale'])
        logit = float(z @ np.array(c['weight']) + c['bias'])
        score = float(1/(1+np.exp(-np.clip(logit, -80, 80))))
        return {'score': score, 'threshold': self.threshold, 'accepted': score >= self.threshold,
                'calibrated': False}


def train(data_root, checkpoint, out, steps=500):
    root, out = Path(data_root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    torch.manual_seed(42)
    meta = json.loads((root/'tiles/meta.json').read_text())
    scenes = sorted({(m['tag'], m['file']) for m in meta})
    random.Random(0).shuffle(scenes)
    nval = int(.12*len(scenes))
    paths = {'part1_oil': root/'zenodo_part1/Images_oil/Oil',
             'part2_lookalike': root/'zenodo_part2/Lookalike'}
    digest = sha256(checkpoint)
    cache = out/'features.npz'
    cache_key = hashlib.sha256(json.dumps([digest, scenes, 'overview512-encoder256-mean-std-rawstats-v1']).encode()).hexdigest()
    if cache.exists():
        saved = np.load(cache, allow_pickle=False)
        if str(saved['cache_key']) != cache_key:
            raise ValueError('Feature cache does not match checkpoint or split; use a new output directory')
        X, y = saved['X'], saved['y']
    else:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = load_model(checkpoint, device)
        X, y, excluded = [], [], []
        feature_dir = out/'feature_cache'/cache_key
        feature_dir.mkdir(parents=True, exist_ok=True)
        from concurrent.futures import ThreadPoolExecutor
        def extract_one(scene):
            tag, name = scene
            cached = feature_dir/f'{tag}_{name}.npy'
            try:
                if cached.exists():
                    features = np.load(cached, allow_pickle=False)
                else:
                    features = extract_features(model, paths[tag]/name, device)
                    np.save(cached, features)
                return features, None
            except (rasterio.errors.RasterioIOError, ValueError) as exc:
                return np.full(1045, np.nan, dtype=np.float32), str(exc)
        with ThreadPoolExecutor(max_workers=3) as pool:
            for i, ((tag, name), (features, error)) in enumerate(zip(scenes, pool.map(extract_one, scenes))):
                if error:
                    print(f'EXCLUDED {tag}/{name}: {error}', flush=True)
                    excluded.append({'tag': tag, 'file': name, 'reason': error})
                X.append(features)
                y.append(int(tag == 'part1_oil'))
                if (i+1) % 25 == 0:
                    print(f'features {i+1}/{len(scenes)}', flush=True)
        X, y = np.array(X), np.array(y, dtype=np.float32)
        np.savez_compressed(cache, X=X, y=y, cache_key=cache_key)
        (out/'excluded.json').write_text(json.dumps(excluded, indent=2))
        del model
        if device.type == 'cuda':
            torch.cuda.empty_cache()
    valid = np.isfinite(X).all(axis=1)
    nval = int(valid[:nval].sum())
    scenes = [s for s, keep in zip(scenes, valid) if keep]
    X, y = X[valid], y[valid]
    if len(np.unique(y[:nval])) < 2 or len(np.unique(y[nval:])) < 2:
        raise ValueError('Both classes must remain in train and validation after exclusions')
    mean, scale = X[nval:].mean(0), X[nval:].std(0)
    scale = np.maximum(scale, 1e-5)
    x = torch.from_numpy((X-mean)/scale)
    target = torch.from_numpy(y)
    torch.manual_seed(42)  # independent of whether encoder features came from cache
    head = torch.nn.Linear(x.shape[1], 1)
    opt = torch.optim.AdamW(head.parameters(), lr=.01, weight_decay=.1)
    pos_weight = torch.tensor(float((y[nval:]==0).sum()/y[nval:].sum()))
    best_loss, best_state, best_step = float('inf'), None, 0
    for step in range(steps):
        opt.zero_grad()
        logits = head(x[nval:])[:, 0]
        loss = F.binary_cross_entropy_with_logits(logits, target[nval:], pos_weight=pos_weight)
        loss.backward()
        opt.step()
        with torch.no_grad():
            val_loss = F.binary_cross_entropy_with_logits(head(x[:nval])[:, 0], target[:nval]).item()
        if val_loss < best_loss:
            best_loss, best_step = val_loss, step+1
            best_state = {k: v.detach().clone() for k, v in head.state_dict().items()}
    head.load_state_dict(best_state)
    # Calibrate in the same float64 arithmetic as the serialized runtime classifier.
    standardized = (X[:nval]-mean.astype(float))/scale.astype(float)
    weight = head.weight.detach().numpy()[0].astype(float)
    bias = float(head.bias.detach()[0])
    scores = 1/(1+np.exp(-np.clip(standardized @ weight + bias, -80, 80)))
    threshold = calibrate_threshold(scores, y[:nval])
    result = metrics(binary_counts(scores >= threshold, y[:nval].astype(bool)))
    config = {'version': 1, 'architecture': 'frozen_resnet34_scene_logistic',
              'segmentation_sha256': digest, 'feature_version': 'overview512-encoder256-mean-std-rawstats-v1',
              'threshold': threshold, 'mean': mean.tolist(), 'scale': scale.tolist(),
              'weight': head.weight.detach().numpy()[0].tolist(), 'bias': float(head.bias.detach()[0]),
              'best_step': best_step, 'validation_loss': best_loss,
              'train_scenes': len(scenes)-nval, 'validation_scenes': nval, 'excluded_scenes': int((~valid).sum()),
              'validation_metrics': result, 'threshold_rule': 'validation boundary retaining >=95% oil recall, with midpoint margin and runtime arithmetic',
              'limitations': 'Scene gate can suppress small spills. Scores are uncalibrated. Validation is scene-separated, not event-separated. No Part III data used for fitting.'}
    (out/'verifier.json').write_text(json.dumps(config, indent=2, allow_nan=False))
    (out/'split.json').write_text(json.dumps({'validation': scenes[:nval], 'train': scenes[nval:]}, indent=2))
    print(json.dumps({k: config[k] for k in ['train_scenes', 'validation_scenes', 'best_step', 'threshold', 'validation_metrics']}, indent=2), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', default='data')
    ap.add_argument('--ckpt', default='runs/spill_unet_tiles.pt')
    ap.add_argument('--out', default='runs/scene_verifier')
    ap.add_argument('--steps', type=int, default=500)
    a = ap.parse_args()
    train(a.data, a.ckpt, a.out, a.steps)
