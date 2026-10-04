"""Self-check for the bits that fail silently: metric math and mask/aug integrity."""
import tempfile
from pathlib import Path
import cv2
import torch, numpy as np
from training.train_spill import evaluate, SpillSet


class Const(torch.nn.Module):
    def __init__(self, v): super().__init__(); self.v = v
    def forward(self, x): return torch.full((x.shape[0], 1, *x.shape[2:]), self.v)


def test_metrics():
    dev = torch.device("cpu")
    y = torch.zeros(2, 1, 4, 4); y[:, :, :2] = 1          # half positive
    x = torch.zeros(2, 3, 4, 4)
    ld = [(x, y)]
    # predict-all-1 => IoU = 0.5, Dice = 2*8/(16+8) = 0.667
    i, d = evaluate(Const(10.0), ld, dev)
    assert abs(i - 0.5) < 1e-6, i
    assert abs(d - 2 / 3) < 1e-6, d
    # predict-all-0 => both 0
    i, d = evaluate(Const(-10.0), ld, dev)
    assert i == 0 and d == 0, (i, d)
    # perfect prediction => 1.0
    class Perfect(torch.nn.Module):
        def forward(self, _): return (y - 0.5) * 20
    i, d = evaluate(Perfect(), ld, dev)
    assert abs(i - 1) < 1e-6 and abs(d - 1) < 1e-6, (i, d)


def test_dataset():
    # A self-contained asymmetric fixture exposes image/mask augmentation desynchronization.
    with tempfile.TemporaryDirectory() as directory:
        image = Path(directory)/'image.png'
        label = Path(directory)/'label.png'
        mask = np.zeros((256, 256), np.uint8)
        mask[12:100, 27:76] = 255
        pixels = np.repeat(mask[..., None], 3, axis=2)
        assert cv2.imwrite(str(image), pixels) and cv2.imwrite(str(label), mask)
        items = [(str(image), str(label))]
        ds = SpillSet(items, aug=True)
        for _ in range(12):
            x, y = ds[0]
            assert x.shape == (3, 256, 256) and y.shape == (1, 256, 256)
            assert x.dtype == y.dtype == torch.float32
            assert 0 <= x.min() and x.max() <= 1
            assert set(torch.unique(y).tolist()) <= {0., 1.}
            assert torch.equal(x[0], y[0]), 'augmentation moved image and mask differently'
            assert int(y.sum()) == int((mask > 0).sum())


if __name__ == "__main__":
    test_metrics(); test_dataset(); print("all checks passed")
