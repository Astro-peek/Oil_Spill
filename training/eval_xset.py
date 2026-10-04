"""Evaluate any checkpoint against any test split, so model quality is separable from label quality."""
import argparse, torch
from torch.utils.data import DataLoader
import segmentation_models_pytorch as smp
from training.train_spill import pairs, SpillSet, evaluate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True, choices=["sos", "refined"])
    a = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ck = torch.load(a.ckpt, map_location=dev)
    model = smp.Unet(ck.get("encoder", "resnet34"), encoder_weights=None, in_channels=3, classes=1).to(dev)
    model.load_state_dict(ck["model"])

    for sens in [["palsar"], ["sentinel"], ["palsar", "sentinel"]]:
        dl = DataLoader(SpillSet(pairs("test", sens, a.data)), batch_size=16, num_workers=4)
        i, d = evaluate(model, dl, dev)
        print(f"  {'+'.join(sens):18s} IoU={i:.4f} Dice={d:.4f}")


if __name__ == "__main__":   # required: py3.14 uses forkserver, workers re-import this module
    main()
