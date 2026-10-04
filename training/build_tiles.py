"""Pass 2: extract a balanced tile cache from Parts I/II into flat memmaps.

Channels are the real reason Part I/II matter: VV, VH and the VV-VH dB difference. SOS only ever
had a replicated grey band, which is why the SOS model cannot tell a slick from a wind shadow --
cross-pol behaves differently over oil than over a low-wind look-alike.
"""
import json, os, warnings, random
import numpy as np, rasterio
warnings.filterwarnings("ignore")
from oilspill.predict_scene import to_uint8

T = 256
D = "data"
OUT = f"{D}/tiles"
PATHS = {
    "part1_oil":       (f"{D}/zenodo_part1/Images_oil/Oil", f"{D}/zenodo_part1/Mask_oil"),
    "part2_lookalike": (f"{D}/zenodo_part2/Lookalike",      f"{D}/zenodo_part2/Mask_lookalike"),
}
POS_MIN   = 0.005     # a tile counts as positive above this oil fraction
N_NEG_P1  = 10000     # clean water from the oil scenes
N_NEG_P2  = 14000     # look-alikes: the hard negatives


def scene_channels(img_path):
    """VV, VH, VV-VH -> 3x uint8, each percentile-stretched exactly as at inference."""
    with rasterio.open(img_path) as s:
        vv = s.read(1).astype(np.float32)
        vh = s.read(2).astype(np.float32) if s.count > 1 else vv
    return np.dstack([to_uint8(vv), to_uint8(vh), to_uint8(vv - vh)])


def main():
    idx = json.load(open("runs/tile_index.json"))
    rng = random.Random(0)
    pos = [r for r in idx if r[4] > POS_MIN]
    neg1 = [r for r in idx if r[4] == 0 and r[0] == "part1_oil"]
    neg2 = [r for r in idx if r[4] == 0 and r[0] == "part2_lookalike"]
    rng.shuffle(neg1); rng.shuffle(neg2)
    sel = pos + neg1[:N_NEG_P1] + neg2[:N_NEG_P2]
    rng.shuffle(sel)
    n = len(sel)
    print(f"tiles: pos={len(pos)} neg_part1={min(len(neg1),N_NEG_P1)} "
          f"neg_lookalike={min(len(neg2),N_NEG_P2)} total={n} ({len(pos)/n*100:.1f}% positive)")

    os.makedirs(OUT, exist_ok=True)
    X = np.lib.format.open_memmap(f"{OUT}/images.npy", "w+", np.uint8, (n, T, T, 3))
    Y = np.lib.format.open_memmap(f"{OUT}/masks.npy", "w+", np.uint8, (n, T, T))

    # group by scene so each 32 MB scene is read exactly once
    by_scene = {}
    for i, r in enumerate(sel):
        by_scene.setdefault((r[0], r[1]), []).append((i, r[2], r[3]))

    for k, ((tag, name), items) in enumerate(by_scene.items(), 1):
        idir, mdir = PATHS[tag]
        try:
            ch = scene_channels(os.path.join(idir, name))
            with rasterio.open(os.path.join(mdir, name)) as s:
                m = (s.read(1) > 0).astype(np.uint8)
        except Exception as e:
            print(f"  [skip] {tag}/{name}: {e}")
            continue
        for i, y, x in items:
            X[i] = ch[y:y+T, x:x+T]
            Y[i] = m[y:y+T, x:x+T]
        if k % 200 == 0:
            print(f"  scenes {k}/{len(by_scene)}", flush=True)

    X.flush(); Y.flush()
    json.dump([{"tag": r[0], "file": r[1], "y": r[2], "x": r[3], "oilfrac": r[4]} for r in sel],
              open(f"{OUT}/meta.json", "w"))
    print(f"-> {OUT}/images.npy {X.shape}, masks.npy, meta.json")


if __name__ == "__main__":
    main()
