"""Pass 1: index every 256x256 tile of Parts I/II by its oil fraction, so we can sample a
training set with a REALISTIC class balance instead of SOS's 97%-positive crops."""
import glob, json, os, sys, warnings
import numpy as np, rasterio
warnings.filterwarnings("ignore")
T = 256

def index(mask_glob, tag):
    rows = []
    files = sorted(glob.glob(mask_glob))
    for n, f in enumerate(files, 1):
        with rasterio.open(f) as s:
            m = s.read(1) > 0
        H, W = m.shape
        for y in range(0, H - T + 1, T):
            for x in range(0, W - T + 1, T):
                rows.append((tag, os.path.basename(f), y, x, float(m[y:y+T, x:x+T].mean())))
        if n % 200 == 0:
            print(f"  {tag} {n}/{len(files)}", flush=True)
    return rows

if __name__ == "__main__":
    D = "data"
    out = []
    out += index(f"{D}/zenodo_part1/Mask_oil/*.tif", "part1_oil")
    out += index(f"{D}/zenodo_part2/Mask_lookalike/*.tif", "part2_lookalike")
    fr = np.array([r[4] for r in out])
    print(f"\ntotal tiles={len(out)}")
    for lo, hi in [(0, 0), (0, 0.005), (0.005, 0.05), (0.05, 0.2), (0.2, 1.01)]:
        sel = (fr == 0) if hi == 0 else ((fr > lo) & (fr <= hi))
        print(f"  oilfrac {'==0' if hi==0 else f'{lo:.3f}-{hi:.2f}'}: {sel.sum():7d} ({sel.mean()*100:5.2f}%)")
    json.dump(out, open("runs/tile_index.json", "w"))
    print("-> runs/tile_index.json")
