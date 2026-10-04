"""Train the slick segmenter on the Part I/II tile cache: calibrated dual-pol input, realistic
class balance, and look-alike hard negatives. Replaces the SOS-trained model, which flagged
look-alikes MORE strongly than real oil (see runs/ diagnostics)."""
import argparse, json, os, random
import numpy as np, torch
from torch.utils.data import Dataset, DataLoader
import segmentation_models_pytorch as smp
from training.train_spill import evaluate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES = os.path.join(ROOT, "data/tiles")


class TileSet(Dataset):
    def __init__(self, idxs, aug=False):
        self.idxs, self.aug = idxs, aug
        self.X = self.Y = None                     # opened lazily, per worker

    def __len__(self):
        return len(self.idxs)

    def __getitem__(self, k):
        if self.X is None:
            self.X = np.load(f"{TILES}/images.npy", mmap_mode="r")
            self.Y = np.load(f"{TILES}/masks.npy", mmap_mode="r")
        i = self.idxs[k]
        img, msk = np.asarray(self.X[i]), np.asarray(self.Y[i])
        if self.aug:
            if random.random() < 0.5: img, msk = img[:, ::-1], msk[:, ::-1]
            if random.random() < 0.5: img, msk = img[::-1], msk[::-1]
            r = random.randint(0, 3)
            if r: img, msk = np.rot90(img, r), np.rot90(msk, r)
        img = np.ascontiguousarray(img.transpose(2, 0, 1), dtype=np.float32) / 255.0
        msk = np.ascontiguousarray(msk > 0, dtype=np.float32)[None]
        return torch.from_numpy(img), torch.from_numpy(msk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--bs", type=int, default=24)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--out", default="runs/spill_unet_tiles.pt")
    a = ap.parse_args()

    meta = json.load(open(f"{TILES}/meta.json"))
    # split by SCENE, never by tile: tiles from one scene overlap in content and would leak
    scenes = sorted({(m["tag"], m["file"]) for m in meta})
    random.Random(0).shuffle(scenes)
    val_scenes = set(scenes[:int(0.12 * len(scenes))])
    tr = [i for i, m in enumerate(meta) if (m["tag"], m["file"]) not in val_scenes]
    va = [i for i, m in enumerate(meta) if (m["tag"], m["file"]) in val_scenes]
    pos_tr = sum(meta[i]["oilfrac"] > 0 for i in tr)
    print(f"scenes={len(scenes)} val_scenes={len(val_scenes)} | train={len(tr)} "
          f"({pos_tr/len(tr)*100:.1f}% pos) val={len(va)}")

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = smp.Unet(a.encoder, encoder_weights="imagenet", in_channels=3, classes=1).to(dev)
    tl = DataLoader(TileSet(tr, True), batch_size=a.bs, shuffle=True, num_workers=4,
                    pin_memory=True, drop_last=True, persistent_workers=True)
    vl = DataLoader(TileSet(va), batch_size=a.bs, num_workers=4, persistent_workers=True)

    dice = smp.losses.DiceLoss("binary")
    bce = torch.nn.BCEWithLogitsLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    best = 0.0
    for ep in range(1, a.epochs + 1):
        model.train(); tot = 0.0
        for x, y in tl:
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast("cuda", torch.float16, enabled=dev.type == "cuda"):
                o = model(x); loss = dice(o, y) + bce(o, y)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            tot += loss.item()
        sch.step()
        iou, dsc = evaluate(model, vl, dev)
        print(f"ep{ep:>3} loss={tot/len(tl):.4f} val_IoU={iou:.4f} val_Dice={dsc:.4f}", flush=True)
        if iou > best:
            best = iou
            torch.save({"model": model.state_dict(), "encoder": a.encoder, "val_iou": iou}, a.out)
    print(f"BEST val_IoU={best:.4f} -> {a.out}")


if __name__ == "__main__":
    main()
