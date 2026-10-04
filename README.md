# Oil Spill Detection and Polluter Tracing (SIH 26143)

This project takes a **radar satellite image of the sea** and:

1. **Finds oil slicks** in it, using an AI model we trained.
2. **Measures each slick**: area, length, width, direction and shape, in real km.
3. **Predicts where the oil will drift next**, and **traces it backward** to find where and when it was probably dumped.
4. **Ranks nearby ships** by how well their movements match that place and time, using ship tracking (AIS) data.
5. Runs **from the terminal**, or from a **simple desktop window** (prototype GUI).

> For a deeper walkthrough, including simple explanations of every term, the reasons behind each choice and likely judge questions with answers, read **[docs/EXPLAINED.md](docs/EXPLAINED.md)**.

---

## Quickstart (any machine, ~5 minutes)

No GPU, no external disk and no dataset download needed. Copy-paste the whole block:

```bash
git clone git@github.com:DorianAarno/sih_oil_spill.git
cd sih_oil_spill
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/fetch_assets.sh
.venv/bin/python -m oilspill.ai_pipeline \
  --image demo_data/Images/Oil/00023.tif --out runs/demo --demo \
  --ais runs/smoke_inputs/synthetic_ais.csv --when 2026-06-12T06:00:00Z
```

Expected output, and the number to check against:

```json
{
  "image": "00023.tif", "crs": "EPSG:4326", "detected": true, "n_slicks": 1,
  "total_area_km2": 29.9288,
  "centroid_lon": 38.908996, "centroid_lat": 20.826883
}
```

If you get `29.9288`, the whole chain works: U-Net detection → slick geometry → drift
hindcast → AIS ship ranking. Full outputs land in `runs/demo/`.

Then confirm the checks pass (about a minute):

```bash
for t in tests/test_*.py; do .venv/bin/python -m tests.$(basename $t .py) || break; done
```

**Note:** this repository is private, so `fetch_assets.sh` needs the [GitHub CLI](https://cli.github.com)
logged in (`gh auth login`) to reach the Release assets. If the repo is made public, plain `curl`
works and no login is needed.

---

## 1. The idea in one picture

```
 Sentinel-1 radar image (VV + VH bands, georeferenced)
        │
        ▼
 ┌──────────────────────┐   oilspill/predict_scene.py
 │ 1. DETECT            │   U-Net AI model slides over the image
 │    oil pixels        │   → probability map → yes/no mask
 └──────────────────────┘
        │                    (optional) oilspill/scene_verifier.py
        │                    second model that rejects look-alikes
        ▼
 ┌──────────────────────┐   oilspill/spill_geometry.py
 │ 2. MEASURE           │   mask → polygons → area, perimeter,
 │    each slick        │   length, width, direction, shape scores
 └──────────────────────┘
        │
        ▼
 ┌──────────────────────┐   oilspill/drift.py + oilspill/ocean_field.py
 │ 3. DRIFT             │   drop virtual particles into the slick,
 │    forward + backward│   move them with currents + 3% of wind
 └──────────────────────┘   → future spread + likely origin & age
        │
        ▼
 ┌──────────────────────┐   oilspill/ais.py
 │ 4. FIND SHIPS        │   keep ships near origin at origin time,
 │    and rank them     │   score 0–100 on 5 clear clues
 └──────────────────────┘
        │
        ▼
   analysis.json, GeoTIFF masks, GeoJSON maps   (shown in gui.py)
```

`oilspill/ai_pipeline.py` runs all four steps in order with one command.

---

## 2. Folder layout

```
oil_spill/
├── README.md               ← you are here
├── gui.py                  simple desktop window to run the AI (prototype)
├── requirements.txt        Python packages (exact versions we used)
├── models.json             list of trained model files + their checksums
│
├── oilspill/               THE CORE SYSTEM (everything the pipeline needs)
│   ├── ai_pipeline.py      main entry point: runs detect → measure → drift → ships
│   ├── predict_scene.py    loads the U-Net, slides it over a full image
│   ├── scene_verifier.py   optional look-alike filter (trains + runs)
│   ├── spill_geometry.py   turns a mask into measured slick polygons
│   ├── drift.py            particle drift physics, forecast + hindcast
│   ├── ocean_field.py      reads real current/wind files (NetCDF) safely
│   ├── ais.py              ship-track loading, filtering, suspect scoring
│   └── metrics.py          small shared helpers: IoU/Dice counts, file hashes
│
├── training/               HOW THE MODEL WAS BUILT
│   ├── index_tiles.py      step 1: cut every scene into 256×256 tiles, record oil %
│   ├── build_tiles.py      step 2: pick a balanced set of 37,910 tiles, save to disk
│   ├── train_tiles.py      step 3: train the U-Net (the model we use)
│   ├── train_spill.py      older model trained on the SOS dataset (replaced)
│   └── eval_xset.py        cross-check used to study the older SOS model
│
├── evaluation/             HOW WE MEASURED ACCURACY
│   ├── evaluate_ai.py      runs the model on the 450 test scenes, writes reports
│   └── evaluate_verifier.py  same test, with the look-alike filter switched on
│
├── tests/                  43 automatic checks (run them before a demo)
├── docs/                   accuracy report, model card, planned API
├── scripts/                fetch_assets.sh (model + demo scenes), dataset download helpers
├── runs/                   saved model, evaluation reports (outputs)
├── demo_data/              3 test scenes, downloaded by scripts/fetch_assets.sh
└── data → external HDD     full datasets (symlink; ~100 GB, optional)
```

**Rule of thumb:** `oilspill/` is the product, `training/` and `evaluation/` show how we built and proved it, and `gui.py` is the prototype front end.

---

## 3. Setup

On any machine, from a fresh clone. Built and tested on Python 3.14 with an RTX 3060; the pinned
versions in `requirements.txt` are what we used, and CPU-only machines work too:

```bash
git clone git@github.com:DorianAarno/sih_oil_spill.git && cd sih_oil_spill
python -m venv .venv
.venv/bin/pip install torch torchvision          # plain PyPI build, includes CUDA
.venv/bin/pip install -r requirements.txt
./scripts/fetch_assets.sh                        # ~160 MB: trained model + 3 demo scenes
```

`torch` and `torchvision` are pinned in `requirements.txt` and install from plain PyPI with CUDA
included. On a machine with no NVIDIA GPU the same wheels run on CPU; a demo scene takes roughly a
minute instead of seconds.

`fetch_assets.sh` pulls the 94 MB U-Net and the demo scenes from the GitHub Release (they are
too large for git), then checks the model against the SHA-256 in `models.json`. It is safe to
re-run. After it finishes the demo below works with **no external disk and no GPU**.

The CPU also works, just more slowly. **Run every command from the project root folder**, using
`python -m folder.file`. That is how the folders find each other.

`data/` is a symlink to an external disk holding the full ~100 GB datasets. It is needed only for
retraining and for the full 450-scene benchmark, not for the demo or the tests.

---

## 4. How to run it

### Detect oil in one image (the main command)

```bash
.venv/bin/python -m oilspill.ai_pipeline \
  --image demo_data/Images/Oil/00023.tif \
  --out runs/my_detection
```

This writes into `runs/my_detection/`, which must be a new or empty folder:

| File | What it is |
|---|---|
| `analysis.json` | everything: each slick's measurements, settings, which steps ran, file hashes |
| `probability.tif` | the AI's raw 0–1 score for every pixel |
| `mask.tif` | final yes/no oil map (after the threshold and removing tiny specks) |
| `slicks.geojson` | slick outlines on a world map (lat/lon) with measurements |
| `drift.geojson` | future spread, backward track and origin guesses (only if drift ran) |

### Full run: detection, drift and ships

```bash
.venv/bin/python -m oilspill.ai_pipeline \
  --image scene.tif --when 2026-01-01T12:00:00Z \
  --currents currents.nc --wind wind.nc --ais ais.csv \
  --out runs/my_analysis --forecast-hours 24 --hindcast-hours 24
```

- `--when`: when the satellite took the picture (UTC). Drift needs it.
- `--currents`: ocean current file with `uo`/`vo` in m/s (for example Copernicus Marine).
- `--wind`: wind file with `u10`/`v10` in m/s (for example ERA5).
- `--ais`: ship positions CSV with columns `MMSI, BaseDateTime, LAT, LON, SOG, COG` (MarineCadastre format).
- `--verifier runs/scene_verifier/verifier.json` turns on the look-alike filter.

If a file is missing, the pipeline **does not make anything up**. For example, without currents the drift step is marked `missing_currents` and skipped.

### Demo mode (synthetic currents, for showing that everything connects)

```bash
.venv/bin/python -m oilspill.ai_pipeline \
  --image demo_data/Images/Oil/00023.tif --out runs/my_demo \
  --when 2026-06-12T06:00:00Z --demo \
  --ais runs/smoke_inputs/synthetic_ais.csv
```

This is the headline demo: it needs only `scripts/fetch_assets.sh`, and finds one 29.93 km² slick
in the Oil/00023 scene. `demo_data/` also carries a look-alike and a clean-sea scene, so the same
command can show the false-alarm behaviour honestly. A finished example is in `runs/ai_smoke_demo/`.

### Use the prototype GUI

```bash
.venv/bin/python gui.py
```

1. Click **…** next to *SAR image* and pick a VV+VH GeoTIFF (for example `demo_data/Images/Oil/00023.tif`).
2. Optional: add currents, wind and AIS files, or tick **Demo drift** to use synthetic currents.
3. Press **Run analysis**. The middle shows the image with detected oil in **red**. The right side lists each slick's measurements, the estimated origin and the top-ranked ships.

Each run's files are saved in `runs/gui/<date-time>/`, the same outputs as the terminal command. The GUI only collects inputs and calls `oilspill/ai_pipeline.py`, so the terminal and GUI always give identical results.

### Run the tests (about a minute, no GPU or datasets needed)

```bash
for t in tests/test_*.py; do .venv/bin/python -m tests.$(basename $t .py) || break; done
```

### Measure accuracy on the test set

```bash
.venv/bin/python -m evaluation.evaluate_ai --per-class 15 --out runs/eval_quick   # 45 scenes
.venv/bin/python -m evaluation.evaluate_ai --per-class 0  --out runs/eval_full    # all 450
```

### Retrain the model from scratch

Needs the Zenodo Part I and II datasets and several hours of GPU time.

```bash
.venv/bin/python -m training.index_tiles
.venv/bin/python -m training.build_tiles
.venv/bin/python -m training.train_tiles --out runs/spill_unet_tiles_new.pt
.venv/bin/python -m oilspill.scene_verifier --out runs/scene_verifier_new   # optional filter
```

---

## 5. Data we used

| Dataset | What's in it | Used for |
|---|---|---|
| **Zenodo Sentinel-1 Oil Spill, Part I** | 1,200 real oil-spill scenes, North Sea, 2048×2048 px, VV+VH radar, with oil masks | training |
| **Zenodo Part II** | 685 **look-alike** scenes (things that look like oil but aren't) | training (hard examples) |
| **Zenodo Part III** | 150 oil + 150 look-alike + 150 clean-sea scenes, **Eastern Mediterranean and Red Sea** | final test only |
| Deep-SAR SOS (+ refined masks) | 8,070 small pre-cropped patches | first model (later replaced, see below) |

The test scenes come from **different seas** than the training scenes, so the test checks whether the model works in new places.

---

## 6. Results (450 test scenes, Part III)

| | Default model | With look-alike filter |
|---|---:|---:|
| Oil scenes found | **147 / 150 (98%)** | 111 / 150 (74%) |
| Look-alike scenes wrongly flagged | 77 / 150 | **11 / 150** |
| Clean-sea scenes wrongly flagged | 17 / 150 | **8 / 150** |
| Scene accuracy | 78.4% | **87.1%** |
| Precision (flags that were real oil) | 61.0% | **85.4%** |
| Pixel IoU on oil scenes (outline overlap) | **73.2%** | – |

**How to read this:** the default model almost never misses a spill, but it also raises false alarms on look-alikes. The filter removes most false alarms but misses more real spills. We keep the default **on** because a missed spill costs more than a false alarm a human can dismiss, and the filter is one flag away.

Full numbers: [docs/ACCURACY_REPORT.md](docs/ACCURACY_REPORT.md), [runs/evaluation_full/REPORT.md](runs/evaluation_full/REPORT.md).

---

## 7. What is real and what is not yet (be upfront about this)

| Part | Status |
|---|---|
| Oil detection AI | **Trained and tested** on 450 real, labelled scenes from unseen seas |
| Slick measurements | **Done**, checked by tests against shapes with known answers |
| Drift physics | **Done** and checked against hand-calculated answers. So far run only with **synthetic** currents: the ERA5 wind download needs a one-time licence click, and real currents need a Copernicus Marine account |
| Ship scoring | **Done**. So far demonstrated only with **synthetic** AIS (the problem statement allows this) |
| GUI | **Prototype**: a single tkinter window, no maps. It shows the detection overlay and a text report |
| Optical (EO) images, ship detection from radar, web API | **Not built**. An API design exists in `docs/API_PLAN.md` |

Vessel scores are **investigation leads, not proof**.

---

## 8. Glossary

- **SAR**: Synthetic Aperture Radar. The satellite sends radar pulses and records the echo. It works at night and through clouds.
- **VV / VH**: two radar "channels". VV sends and receives vertically. VH sends vertically and receives horizontally.
- **Sigma0 (dB)**: how strongly the sea surface bounces radar back. Oil makes the sea smoother, so the image is darker.
- **Look-alike**: a dark patch that isn't oil, such as a calm low-wind area, algae, or rain cells.
- **U-Net**: an image AI that outputs a label for every pixel (oil / not oil).
- **IoU**: overlap of predicted and true oil ÷ their combined area. 1.0 is perfect.
- **Hindcast**: running the drift model backward in time.
- **AIS**: the radio system ships use to broadcast position, speed and heading.
- **MMSI**: a ship's unique AIS ID number.
- **CPA**: closest point of approach, the nearest a ship came to the origin point.

## Web app (backend + frontend)

```bash
cd backend && npm install && npm start          # API on :4000, needs backend/.env (Supabase keys)
python3 -m http.server 5500 -d frontend         # open http://localhost:5500/command-center.html
```

`POST /api/v1/investigations/:id/analyze` runs `python -m oilspill.web_bridge` (real U-Net → drift → AIS
ranking) and stores the result in Supabase. Upload a Sentinel-1 VV/VH GeoTIFF, or run without one to get a
synthetic scene at the typed lat/lon. Drift uses the wind/current sliders as uniform forcing; AIS is synthetic.
Set `OILSPILL_DEVICE=cuda` to use the GPU (defaults to CPU).
