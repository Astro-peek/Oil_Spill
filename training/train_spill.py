"""Oil spill segmentation on the Deep-SAR SOS dataset. Deliverable (a): detect + outline the slick."""
import argparse, glob, os, random
import cv2, numpy as np, torch
from torch.utils.data import Dataset, DataLoader
import segmentation_models_pytorch as smp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOS = os.path.join(ROOT, "data/spill_sos/dataset")
REF = os.path.join(ROOT, "data/spill_sos_refined")


def pairs(split, sensors, data="sos"):
    out = []
    if data == "refined":
        # refined SOS is flat: images/<split>/<sensor>_<n>.png with an identically named mask.
        # Its "val" split is the ORIGINAL test split (776 palsar + 839 sentinel), so scores here
        # are directly comparable to the sos run's TEST numbers.
        split = {"test": "val"}.get(split, split)
        for s in sensors:
            for i in sorted(glob.glob(f"{REF}/images/{split}/{s}_*.png")):
                m = i.replace("/images/", "/masks/")
                if os.path.exists(m):
                    out.append((i, m))
        return out
    for s in sensors:
        ims = sorted(glob.glob(f"{SOS}/{split}/{s}/image/*"))
        for i in ims:
            l = i.replace("/image/", "/label/")
            if os.path.exists(l):
                out.append((i, l))
    return out


class SpillSet(Dataset):
    def __init__(self, items, aug=False):
        self.items, self.aug = items, aug

    def __len__(self):
        return len(self.items)

    def __getitem__(self, k):
        ip, lp = self.items[k]
        img = cv2.imread(ip, cv2.IMREAD_COLOR)
        msk = cv2.imread(lp, cv2.IMREAD_GRAYSCALE)
        if self.aug:  # flips + rot90 only: SAR slicks have no canonical orientation
            if random.random() < 0.5:
                img, msk = img[:, ::-1], msk[:, ::-1]
            if random.random() < 0.5:
                img, msk = img[::-1], msk[::-1]
            k90 = random.randint(0, 3)
            if k90:
                img, msk = np.rot90(img, k90), np.rot90(msk, k90)
        img = np.ascontiguousarray(img.transpose(2, 0, 1), dtype=np.float32) / 255.0
        msk = np.ascontiguousarray(msk > 127, dtype=np.float32)[None]
        return torch.from_numpy(img), torch.from_numpy(msk)


@torch.no_grad()
def evaluate(model, loader, dev, thr=0.5):
    """Dataset-level IoU/Dice — accumulate counts, don't average per-image ratios."""
    model.eval()
    ti = tu = tp = tg = ti2 = 0
    for x, y in loader:
        x, y = x.to(dev), y.to(dev)
        with torch.autocast("cuda", torch.float16, enabled=dev.type == "cuda"):
            p = (model(x).sigmoid() > thr).float()
        ti += (p * y).sum().item()
        tu += ((p + y) > 0).float().sum().item()
        tp += p.sum().item()
        tg += y.sum().item()
    iou = ti / max(tu, 1)
    dice = 2 * ti / max(tp + tg, 1)
    return iou, dice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensors", default="palsar,sentinel")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--data", default="sos", choices=["sos", "refined"])
    ap.add_argument("--out", default="runs/spill_unet.pt")
    a = ap.parse_args()

    sensors = a.sensors.split(",")
    tr = pairs("train", sensors, a.data)
    te = pairs("test", sensors, a.data)
    random.Random(0).shuffle(tr)
    nval = int(0.1 * len(tr))
    val, tr = tr[:nval], tr[nval:]
    print(f"data={a.data} train={len(tr)} val={len(val)} test={len(te)} sensors={sensors}")

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = smp.Unet(a.encoder, encoder_weights="imagenet", in_channels=3, classes=1).to(dev)

    dl = lambda d, sh: DataLoader(d, batch_size=a.bs, shuffle=sh, num_workers=4, pin_memory=True, drop_last=sh)
    tl, vl, sl = dl(SpillSet(tr, True), True), dl(SpillSet(val), False), dl(SpillSet(te), False)

    dice_loss = smp.losses.DiceLoss("binary")
    bce = torch.nn.BCEWithLogitsLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    best = 0.0
    for ep in range(1, a.epochs + 1):
        model.train()
        tot = 0.0
        for x, y in tl:
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast("cuda", torch.float16, enabled=dev.type == "cuda"):
                o = model(x)
                loss = dice_loss(o, y) + bce(o, y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            tot += loss.item()
        sched.step()
        iou, dice = evaluate(model, vl, dev)
        print(f"ep{ep:>3} loss={tot/len(tl):.4f} val_IoU={iou:.4f} val_Dice={dice:.4f}", flush=True)
        if iou > best:
            best = iou
            torch.save({"model": model.state_dict(), "encoder": a.encoder, "val_iou": iou}, a.out)

    model.load_state_dict(torch.load(a.out)["model"])
    print(f"BEST val_IoU={best:.4f}")
    for s in sensors:  # per-sensor: PALSAR and Sentinel are different sensors+regions
        t = DataLoader(SpillSet(pairs("test", [s], a.data)), batch_size=a.bs, num_workers=4)
        i, d = evaluate(model, t, dev)
        print(f"TEST[{s}] IoU={i:.4f} Dice={d:.4f}")
    i, d = evaluate(model, sl, dev)
    print(f"TEST[all] IoU={i:.4f} Dice={d:.4f}")


if __name__ == "__main__":
    main()
