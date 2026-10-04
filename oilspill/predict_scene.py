"""Run the patch-trained slick model over full georeferenced Sentinel-1 scenes.

The bridge that makes the model deployable: it was trained on 256x256 8-bit SOS patches, but real
scenes (and Zenodo Parts I/II/III) are 2048x2048 float32 Sigma0 in dB. We stretch dB to 8-bit,
slide the model over the scene with overlap, average the overlaps, and hand the thresholded mask
to spill_geometry for real-world measurement.
"""
import argparse, glob, json, math, os, warnings
import numpy as np, rasterio, torch
import segmentation_models_pytorch as smp
from oilspill.spill_geometry import measure

warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)

# ponytail: fixed percentile stretch as the dB->8bit bridge. It is the main calibration knob
# between training (SOS 8-bit PNGs, unknown stretch) and real Sigma0 scenes. If false alarms are
# sensor-dependent, tune these before touching the model.
LO_PCT, HI_PCT = 2.0, 98.0


def to_uint8(db, lo_pct=LO_PCT, hi_pct=HI_PCT):
    """Per-scene percentile stretch of Sigma0 dB to 8-bit, matching how SAR is normally rendered."""
    finite = np.isfinite(db)
    if not finite.any():
        return np.zeros(db.shape, np.uint8)
    lo, hi = np.percentile(db[finite], [lo_pct, hi_pct])
    if hi <= lo:
        return np.zeros(db.shape, np.uint8)
    out = np.clip((db - lo) / (hi - lo), 0, 1)
    out[~finite] = 0
    return (out * 255).astype(np.uint8)


def scene_channels(img_path):
    """VV, VH, VV-VH as 3x stretched uint8 — the exact input build_tiles.py cached for training.
    Requires both polarizations; use grey mode explicitly for single-band models."""
    with rasterio.open(img_path) as s:
        if s.count < 2:
            raise ValueError("Dual-pol model requires VV and VH bands, in that order")
        vv = s.read(1, masked=True).astype(np.float32).filled(np.nan)
        vh = s.read(2, masked=True).astype(np.float32).filled(np.nan)
    return np.dstack([to_uint8(vv), to_uint8(vh), to_uint8(vv - vh)])


def load_model(ckpt, dev):
    ck = torch.load(ckpt, map_location=dev, weights_only=True)
    m = smp.Unet(ck.get("encoder", "resnet34"), encoder_weights=None, in_channels=3, classes=1)
    m.load_state_dict(ck["model"])
    return m.to(dev).eval()


@torch.no_grad()
def predict(model, img8, dev, tile=256, stride=128, bs=32):
    """img8: (H,W) grey or (H,W,3) multi-channel uint8."""
    if img8.ndim == 2:
        img8 = np.repeat(img8[:, :, None], 3, 2)
    if img8.ndim != 3 or img8.shape[2] != 3 or min(img8.shape[:2]) < 1:
        raise ValueError("Input must be a nonempty HxWx3 image")
    if tile < 32 or tile % 32 or not 0 < stride <= tile or bs < 1:
        raise ValueError("tile must be a positive multiple of 32; 0 < stride <= tile; bs >= 1")
    original_h, original_w = img8.shape[:2]
    img8 = np.pad(img8, ((0, max(0, tile-original_h)), (0, max(0, tile-original_w)), (0, 0)), mode="edge")
    H, W = img8.shape[:2]
    ys = list(range(0, max(H - tile, 0) + 1, stride)) or [0]
    xs = list(range(0, max(W - tile, 0) + 1, stride)) or [0]
    if ys[-1] + tile < H: ys.append(H - tile)
    if xs[-1] + tile < W: xs.append(W - tile)

    prob = np.zeros((H, W), np.float32)
    cnt = np.zeros((H, W), np.float32)
    coords, batch = [], []

    def flush():
        if not batch:
            return
        x = torch.from_numpy(np.stack(batch)).to(dev)
        with torch.autocast("cuda", torch.float16, enabled=dev.type == "cuda"):
            p = model(x).sigmoid().float().cpu().numpy()[:, 0]
        for (yy, xx), pp in zip(coords, p):
            prob[yy:yy + tile, xx:xx + tile] += pp
            cnt[yy:yy + tile, xx:xx + tile] += 1
        coords.clear(); batch.clear()

    for y in ys:
        for x in xs:
            t = img8[y:y + tile, x:x + tile].astype(np.float32) / 255.0
            batch.append(t.transpose(2, 0, 1))
            coords.append((y, x))
            if len(batch) == bs:
                flush()
    flush()
    return (prob / np.maximum(cnt, 1))[:original_h, :original_w]


def run_scene(model, path, dev, channels="dual", **kw):
    """channels='dual' -> VV/VH/VV-VH (models trained by train_tiles.py);
       channels='grey' -> replicated VV (the older SOS-trained models)."""
    if channels == "grey":
        with rasterio.open(path) as s:
            pixels = s.read(1, masked=True).astype(np.float32).filled(np.nan)
            valid = np.isfinite(pixels)
        image = to_uint8(pixels)
    elif channels == "dual":
        image = scene_channels(path)
        with rasterio.open(path) as s:
            bands = s.read([1, 2], masked=True).astype(np.float32).filled(np.nan)
            valid = np.isfinite(bands).all(axis=0)
    else:
        raise ValueError("channels must be dual or grey")
    if not valid.any():
        raise ValueError("Scene has no valid pixels")
    result = predict(model, image, dev, **kw)
    result[~valid] = 0
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="runs/spill_unet_tiles.pt")
    ap.add_argument("--images", required=True)
    ap.add_argument("--truth", default="", help="mask dir; enables IoU scoring")
    ap.add_argument("--truth-suffix", default="_segmentation")
    ap.add_argument("--channels", default="dual", choices=["dual", "grey"])
    ap.add_argument("--thr", type=float, default=0.5)
    ap.add_argument("--min-area-km2", type=float, default=0.05)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--label", default="", help="tag for the report, e.g. Oil / Lookalike / No oil")
    ap.add_argument("--out", default="")
    ap.add_argument("--save-probs", default="", help="dir to cache raw probability maps as .npy")
    a = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(a.ckpt, dev)
    files = sorted(glob.glob(a.images))
    if a.limit:
        files = files[:a.limit]
    if not files:
        ap.error("No images matched the input pattern")
    if a.save_probs:
        os.makedirs(a.save_probs, exist_ok=True)

    rows, inter, union = [], 0.0, 0.0
    for n, f in enumerate(files, 1):
        prob = run_scene(model, f, dev, channels=a.channels)
        if a.save_probs:
            np.save(os.path.join(a.save_probs, os.path.basename(f) + ".npy"), prob.astype(np.float16))
        pred = (prob > a.thr).astype(np.uint8)
        summ, slicks = measure(f, min_area_km2=a.min_area_km2, mask_array=pred)
        summ["max_prob"] = round(float(prob.max()), 4)
        if a.truth:
            stem = os.path.splitext(os.path.basename(f))[0]
            tp = os.path.join(a.truth, f"{stem}{a.truth_suffix}.tif")
            if os.path.exists(tp):
                with rasterio.open(tp) as s:
                    gt = (s.read(1) > 0)
                inter += float((pred.astype(bool) & gt).sum())
                union += float((pred.astype(bool) | gt).sum())
        rows.append(summ)
        if n % 25 == 0:
            print(f"  {n}/{len(files)}", flush=True)

    det = sum(r["detected"] for r in rows)
    tag = a.label or os.path.basename(os.path.dirname(a.images))
    print(f"\n[{tag}] scenes={len(rows)} flagged={det} ({det/max(len(rows),1)*100:.1f}%) "
          f"thr={a.thr} min_area={a.min_area_km2}km2")
    if a.truth and union:
        print(f"[{tag}] pixel IoU vs truth = {inter/union:.4f}")
    areas = [r["total_area_km2"] for r in rows if r["detected"]]
    if areas:
        print(f"[{tag}] flagged area km2: median={np.median(areas):.3f} max={max(areas):.3f}")
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(rows, open(a.out, "w"), indent=1)
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
