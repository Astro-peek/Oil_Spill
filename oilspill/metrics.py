"""Small shared helpers: confusion counts, IoU/Dice-style scores and file hashes."""
import hashlib

import numpy as np


def binary_counts(pred, truth, valid=None):
    pred, truth = np.asarray(pred, bool), np.asarray(truth, bool)
    if pred.shape != truth.shape:
        raise ValueError('Prediction and truth shapes differ')
    valid = np.ones_like(truth) if valid is None else np.asarray(valid, bool)
    return dict(tp=int((pred & truth & valid).sum()), fp=int((pred & ~truth & valid).sum()),
                fn=int((~pred & truth & valid).sum()), tn=int((~pred & ~truth & valid).sum()))


def metrics(c):
    tp, fp, fn, tn = (c[k] for k in ('tp', 'fp', 'fn', 'tn'))
    div = lambda a, b: a / b if b else None
    return {**c, 'accuracy': div(tp+tn, tp+fp+fn+tn), 'precision': div(tp, tp+fp),
            'recall': div(tp, tp+fn), 'specificity': div(tn, tn+fp),
            'iou': div(tp, tp+fp+fn), 'dice': div(2*tp, 2*tp+fp+fn)}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()
