# The Project Explained: A Presenter's Guide

This guide is for **explaining the project out loud**. Each section says what a part does, how it works, why we built it that way, and which numbers to quote. The last sections are a numbers cheat sheet and likely judge questions with answers.

---

## Part 0 · The problem in plain words

Ships sometimes illegally dump oily waste at sea, often at night, sometimes with their tracking transponder switched off. The problem statement (SIH 26143) asks for three things:

- **(a)** Detect the spill in satellite images and describe its shape, plus its age if possible.
- **(b)** Use ocean and weather data to **trace the oil back to where and when it started**, and predict where it goes next.
- **(c)** Use ship tracking (AIS) data to find ships that were near that place at that time, **filter out the irrelevant ones, and score the suspects**.

Plus a visual interface. We built all three parts, which run from the terminal, plus a simple prototype GUI.

---

## Part 1 · Why radar and not normal photos

**Say this:** "Oil is invisible to normal cameras most of the time, but radar sees it clearly."

- A radar satellite (Sentinel-1) sends microwave pulses at the sea. Small wind ripples on the water scatter the pulses back, so the sea looks **bright**.
- Oil forms a thin film that **calms those small ripples**. The calm patch reflects the radar away like a mirror, so oil looks **dark**.
- Radar works **at night and through clouds**. Optical photos fail in both cases, and sun glare on water also confuses them.
- **The catch:** other things also calm the sea and look dark. Examples are very low-wind areas, algae films, rain cells and ship wakes. These are called **look-alikes**, and they are the hardest part of the whole problem.

**Two channels, VV and VH.** Sentinel-1 records two versions of each image:
- **VV**: sent vertical, received vertical. This is the main "brightness" image.
- **VH**: sent vertical, received horizontal. It reacts to the surface differently.

Oil and a calm low-wind patch can look equally dark in VV but behave differently in VH. So we give the model three inputs: **VV, VH, and VV minus VH**. The difference channel makes that contrast easy for the model to see.

---

## Part 2 · The detection AI

### 2.1 The model: U-Net

**Say this:** "A U-Net looks at an image and colours in every pixel as oil or not oil."

- It has two halves. The **encoder** squeezes the image down to learn *what* is there. The **decoder** expands it back to full size to draw *where* it is. "Skip connections" pass fine detail straight across, so the outlines stay sharp.
- Our encoder is **ResNet-34**, starting from weights pre-trained on ImageNet (millions of normal photos). It already knows edges and textures, so it learns radar faster.
- Output: a number from 0 to 1 per pixel. Above **0.5** counts as oil.
- Library: `segmentation-models-pytorch`. Code: `oilspill/predict_scene.py`.

### 2.2 Preparing the image (`to_uint8`)

Radar values are in decibels, roughly −35 to +5. The model expects 0–255 like a normal picture. For each image and each channel we:
1. Find the 2nd and 98th percentile values, which ignores extreme outliers.
2. Stretch that range linearly to 0–255.

We do exactly the same in training and in real use. If the two differ, the model breaks.

### 2.3 Running on a full scene (sliding window)

A scene is 2048×2048 pixels, about 20 km × 20 km at 10 m per pixel. The model was trained on 256×256 tiles, so we:
- Slide a 256×256 window across the image, **moving 128 pixels each time**. Each window overlaps its neighbours by half.
- Run the windows through the GPU in batches of 32.
- **Average** the overlapping predictions. This removes visible seams at tile edges.
- Mark pixels with no data (image borders) as "not oil".

### 2.4 Training data: why we built our own tile set

**This is the most important story in the project.** Tell it.

**First attempt: the SOS dataset.** We first trained on Deep-SAR SOS, 8,070 small patches. It scored **IoU 0.81**, which looks great. Then we ran it on real full scenes:
- It flagged **100% of clean-sea scenes** as containing oil.
- It rated **look-alikes higher than real oil**. The ranking was upside down, so no threshold could fix it.

**Why it failed:** 97% of SOS patches contain oil, because every patch was cropped around a spill. The model learned "there is always oil" instead of "this is what oil looks like". Real scenes average only about **4% oil pixels**.

**A second lesson:** a "refined" SOS version with corrected masks seemed to improve IoU from 0.755 to 0.812. We tested every model against every label set and found that retraining gained only **+0.002**. The +5.7 points came from cleaner **test** labels, not a better model. So we never claim that improvement.

**The fix: build a realistic training set** (`training/index_tiles.py`, `training/build_tiles.py`):
1. Cut all 1,200 oil scenes (Part I) and 685 look-alike scenes (Part II) into 256×256 tiles and record each tile's oil percentage.
2. Select:
   - **13,910** tiles with oil (more than 0.5% oil pixels)
   - **10,000** clean-sea tiles from the oil scenes
   - **14,000** look-alike tiles. These are "hard negatives", deliberately showing the model what is *not* oil.
3. Total **37,910 tiles, 36.7% with oil**. That is a much more honest balance than 97%.

**Split by scene, not by tile.** Tiles cut from the same scene look alike. If some went to training and some to validation, the model would be "tested" on scenes it had already seen. We put whole scenes into validation: 226 of 1,885 scenes (12%).

### 2.5 Training settings (`training/train_tiles.py`)

| Setting | Value | Plain reason |
|---|---|---|
| Loss | Dice loss + binary cross-entropy | Dice handles "oil is a small part of the image"; BCE keeps per-pixel learning stable |
| Optimizer | AdamW, learning rate 3e-4, weight decay 1e-4 | standard, reliable choice |
| Schedule | cosine decay over 25 epochs | learning rate shrinks smoothly toward the end |
| Batch size | 24 | fits in 12 GB of GPU memory |
| Augmentation | random flips and 90° rotations | a slick has no "up", so rotated copies are valid new examples |
| Mixed precision | float16 on GPU | about 2× faster, less memory |
| Best checkpoint | epoch 22, validation **IoU 0.749**, Dice 0.857 | saved to `runs/spill_unet_tiles.pt` |

### 2.6 Removing specks

After the threshold, any connected blob **smaller than 0.05 km²** (about 500 pixels) is dropped. Tiny specks are almost always noise.

### 2.7 The optional look-alike filter (`oilspill/scene_verifier.py`)

**Say this:** "A second, tiny model looks at the whole scene at once and asks: does this scene contain oil at all?"

- It reuses the trained U-Net's **encoder** without changing it ("frozen").
- It shrinks the whole scene to a small overview, runs the encoder, and takes the average and spread of the deepest features (1,024 numbers).
- It adds 21 simple radar statistics: 5 percentiles, mean and standard deviation for each of VV, VH and VV−VH.
- A **logistic regression** (a single weighted sum) turns those 1,045 numbers into a score.
- The cut-off was chosen **only on validation data**, to keep at least **95% of oil scenes**. The value is 0.148.
- If the scene is rejected, the oil mask is cleared, but the raw probability map is still saved for a human to review.

**The trade-off:** false alarms drop a lot (look-alikes flagged fall from 77 to 11), but real spills found drop from 147 to 111. So the filter is **off by default**.

---

## Part 3 · Measuring the slick (`oilspill/spill_geometry.py`)

1. **Mask to polygons:** trace the outline of every connected oil blob.
2. **Convert to real metres:** the image is in latitude/longitude, but degrees are not equal distances. One degree of longitude is about 64 km at the North Sea and about 104 km at the Red Sea. So we convert each slick into the local **UTM zone**, a flat metre-based map projection, before measuring. A test checks this; measuring in degrees would be wrong by up to 2×.
3. **Measurements for each slick:**

| Property | How it's computed | Why it matters |
|---|---|---|
| Area (km²) | polygon area in UTM | size of the spill |
| Perimeter (km) | outline length | how ragged it is |
| Length and width | sides of the **smallest rotated rectangle** that fits around it | overall shape |
| Orientation (°) | direction of the long side (0 = north–south, 90 = east–west) | a moving ship leaves a slick **along its route**, which is used in ship scoring |
| Elongation | length ÷ width | ship discharges are long and thin |
| Solidity | area ÷ convex hull area | 1.0 is a solid shape; lower means broken or feathered |
| Compactness | perimeter ÷ perimeter of a circle with the same area | 1.0 is a circle; higher means stringy, typical of oil |

4. The outlines are saved as **GeoJSON** in WGS84 lat/lon, which any map tool can open.

---

## Part 4 · Drift: forward forecast and backward trace

### 4.1 How the oil moves (`oilspill/drift.py`)

**Say this:** "We drop hundreds of virtual particles into the slick and let the ocean carry them."

The surface oil speed is:

```
oil velocity = ocean current  +  3% × wind velocity
```

- The **3% "windage"** is a standard rule from oil-spill modelling: wind drags surface oil at about 3% of the wind speed.
- **Particles:** 200 random points placed inside the slick outline.
- **Time stepping:** 15-minute steps using **RK2 (midpoint method)**. We check the velocity at the start, take a half step, check again, then take the full step with the midpoint velocity. It is more accurate than a simple straight step, and still cheap.
- **Spreading:** oil spreads through small-scale turbulence. We add a small random jump each step (diffusivity 5 m²/s), a standard "random walk".
- **Uncertainty ensemble:** the run is repeated **3 times**, each with a small random extra current (±0.03 m/s), to show how sensitive the result is. The forecast area is the outline around all particles from all runs at 8 moments in time.

### 4.2 Real current and wind files (`oilspill/ocean_field.py`)

- Reads standard NetCDF files: Copernicus Marine currents (`uo`, `vo`) and ERA5 wind (`u10`, `v10`).
- Interpolates smoothly in time, latitude and longitude.
- **Strict:** if a particle drifts outside the file's area or time range, or hits land (missing values), it **raises an error** instead of silently using zero current.

### 4.3 Tracing back to the origin (hindcast): the clever part

**Running time backward** means moving the particles against the flow.

**How do we know *when* it was released?** A ship dumping oil while moving lays down a **long thin line** of oil. Over time, currents that differ slightly from place to place smear that line wider. So if we run time backward, the slick gets **thinner and thinner until the moment it was released**, then starts getting wider again.

- At each backward step we measure the **width of the particle cloud across its short axis**, using SVD (a standard way to find a cloud's main directions).
- **The moment of minimum width is our release-time estimate**, which answers "age if feasible".
- The cloud's centre at that moment is our **origin location**.

**Honesty built in, and worth saying out loud:**
- If the current were **perfectly uniform**, the slick would just slide as a block and never get thinner, so the release time would be **impossible to recover**. A test proves this.
- The code returns `time_resolved = false` if the thinnest point is at the edge of the search window, meaning "still shrinking, we don't know".
- When timing is unresolved, we **keep 9 candidate origin times** along the backward track and check ships against all of them, instead of pretending to know.

---

## Part 5 · Finding the ship (`oilspill/ais.py`)

### 5.1 AIS data

Ships broadcast their **MMSI (ID), time, latitude, longitude, speed (SOG) and course (COG)**. We read the MarineCadastre CSV format and reject bad rows: impossible positions, invalid IDs, bad speeds.

### 5.2 Filling gaps

Ship positions arrive every few minutes, and sometimes there are gaps. We **estimate positions every 5 minutes between real reports** by straight-line interpolation. Courses are handled correctly across 359° → 1°.

- **Why this matters:** a polluter may **switch AIS off while dumping**. Using only real reports, that ship would look far from the origin. The interpolated path shows it passed right through, and the silence itself becomes evidence.
- Gaps **longer than 6 hours** are not filled, because guessing a route that far is unreliable.

### 5.3 Filtering irrelevant ships

We keep only ships whose track came **within 60 km of the origin** during **origin time ± 6 hours**. In the demo, that is 22 of 41 ships.

### 5.4 Scoring suspects (0–100, fully explainable)

Each clue gives a value from 0 to 1, multiplied by its weight:

| Clue | Weight | How it's scored | Meaning |
|---|---:|---|---|
| **Proximity** | 30 | e^(−closest distance / 15 km) | passed close to the origin |
| **AIS dark gap** | 25 | full points if AIS was silent (≥45 min) *across* the origin time; up to half for other silences in the window | transponder switched off at the key moment |
| **Timing** | 20 | e^(−time difference / 3 h) | was there *when* the release happened |
| **Alignment** | 15 | 1 − (angle between ship course and slick direction) / 90° | a moving ship leaves oil *along* its path |
| **Speed drop** | 10 | (normal speed − slowest speed in window) / 6 knots, capped at 1 | ships often slow down to discharge |

- **Why a weighted sum and not an AI?** It is **transparent**. For every ship we show each clue's value, so an investigator or court can see *why* it ranks high. We also have no real "known culprit" data to train an AI on.
- With several origin guesses, each ship gets its **best** score, plus its average and minimum across guesses.
- Scores are **leads, not probability of guilt**.

### 5.5 Synthetic AIS (allowed by the problem statement)

`synth_traffic()` generates 40 normal ships crossing the area at 8–16 knots, plus **one planted culprit** that passes through the origin at the release time, slows to 6 knots, turns AIS off for 2 hours, and sails along the slick direction. Tests check that the culprit ranks first **and** that giving the wrong release time lowers its score, which proves timing actually matters.

---

## Part 6 · The prototype GUI (`gui.py`)

- A **single desktop window** built with **tkinter**, the GUI toolkit that comes with Python, so nothing extra is installed.
- **Left:** pick the SAR image and optional currents, wind and AIS files, then set the threshold, minimum slick size and drift hours. Tick boxes turn on demo drift, the look-alike filter or CPU-only mode.
- **Run analysis** starts the work in a **background thread**, so the window doesn't freeze while the model runs.
- **Results:** the radar image (VV band) with detected oil painted **red**, plus a text report with each slick's measurements, the origin estimate and the top 5 ships with their scores.
- **Design choice:** the GUI contains **no AI logic**. It calls the same `OilSpillAI.analyze()` as the terminal command, so both always give identical results, and a real web app could later replace the GUI without touching the model.
- A test run on a synthetic scene (a dark streak in noisy sea) on CPU took **8.5 s**. It found the streak (6.9 km long, 0.25 km wide) and ranked the planted culprit ship first (score 81).

---

## Part 7 · Quality checks

- **43 automatic tests** in `tests/`. Most compare the output with **answers you could compute by hand**. Examples:
  - A 1 m/s current for 10 hours must move a particle exactly 36 km.
  - A 100×200-pixel block at 10 m resolution must measure exactly 2 km², 6 km perimeter, orientation 0°.
  - No current and 10 m/s wind at 3% windage must move oil at 0.3 m/s.
  - A uniform current must report "time not resolvable".
  - Pixels with no data must never be marked as oil.
- Every output records **SHA-256 hashes** of the input image, model and AIS file. Any result can be traced back to its exact inputs.
- Evaluation uses a fixed random seed and a fixed threshold, and the **threshold was never tuned on test data**.

---

## Part 8 · Numbers cheat sheet

| Fact | Number |
|---|---|
| Training scenes | 1,200 oil + 685 look-alike (North Sea) |
| Training tiles | 37,910 (13,910 oil / 10,000 clean / 14,000 look-alike) |
| Validation | 226 scenes, 4,511 tiles |
| Best validation IoU / Dice | 0.749 / 0.857 |
| Test set | 450 scenes (150 oil / 150 look-alike / 150 clean), E. Mediterranean and Red Sea |
| Oil scenes found | 147 / 150 = 98% |
| False alarms: look-alike / clean | 77 / 150 and 17 / 150 |
| Scene accuracy / precision | 78.4% / 61.0% |
| Oil-scene pixel IoU | 73.2% |
| With filter: accuracy / precision / recall | 87.1% / 85.4% / 74.0% |
| Old SOS model | IoU 0.81 on patches, but flagged 100% of clean real scenes |
| Scene size / pixel | 2048×2048 px, ~10 m, ~20 km across |
| Windage / particles / step | 3% / 200 / 15 min |
| Ship search | 60 km radius, ±6 h window |
| Score weights | proximity 30, dark gap 25, timing 20, alignment 15, speed drop 10 |
| Tests | 43, all passing |
| GPU | NVIDIA RTX 3060, 12 GB |

---

## Part 9 · Likely judge questions and answers

**Q: Why not use optical satellite images?**
Clouds, night and sun glare make optical unreliable over the sea. Oil is only reliably visible in radar because it calms the ripples radar reflects off. Optical is useful as a second source, but we have not trained an optical model.

**Q: How do you handle look-alikes?**
Three ways. (1) We trained with 14,000 look-alike tiles as hard negatives. (2) We give the model VH and VV−VH, because oil and low-wind patches behave differently in cross-polarisation. (3) An optional scene-level filter cuts look-alike false alarms from 77 to 11 out of 150.

**Q: Your accuracy is 78%. Isn't that low?**
It is honest. The test uses **different seas** from training and includes 300 hard negative scenes. The model finds 98% of real spills. Most errors are look-alikes flagged for human review, and missing a real spill is the worse error. Our first model scored "81% IoU" on an easy benchmark but failed completely on real scenes, so we chose a harder test that reflects reality.

**Q: How do you estimate the age of the spill?**
By running the drift backward. A ship dumping oil while moving leaves a thin line that spreads wider over time. Going backward, the slick is thinnest at release, and that moment gives the age. If the currents contain no information (uniform flow), the system says "not resolved" and keeps several possible times.

**Q: How accurate is the origin?**
We have not measured it on real incidents. That needs real current data and spills with known release points. The physics is verified against hand-calculated cases, and the method refuses to fake an answer when the data can't support one.

**Q: What if the polluter switched off AIS?**
We interpolate each ship's path across silences of up to 6 hours. A ship that went dark near the origin still shows up close, and the silence itself scores up to 25 of 100 points.

**Q: Why not machine learning for ship scoring?**
No dataset of confirmed polluters exists to learn from, and a legal case needs a clear reason. A weighted score with a per-clue breakdown can be explained and checked.

**Q: Is the ship ranking proof?**
No. It is a ranked list of leads for investigators to follow up, for example by checking the ship's logbook or sampling the oil.

**Q: Is the data real?**
The satellite images, masks and test results are real (Zenodo Sentinel-1 dataset). The currents and AIS ships in the demo are synthetic, which the problem statement explicitly allows. The pipeline already accepts real current, wind and AIS files. We only lacked account access (the ERA5 licence acceptance and a Copernicus Marine account).

**Q: How would this work in production?**
`docs/API_PLAN.md` has the design: upload the image, AIS and ocean files, queue a GPU job, poll for the result. The processing core (`OilSpillAI` class) is ready to wrap. The web server is not built yet.

**Q: How long does one scene take?**
About 1.3 seconds per 2048×2048 scene on an RTX 3060 (median over the 450 test scenes; slowest 12 s). Each scene's time is recorded in `runs/evaluation_full/samples.json`.

**Q: What would you improve next?**
(1) Real currents and wind for real incidents. (2) Test on spills with known release times and known culprits. (3) A ship detector on the same radar image, which would put ship and slick in the same picture at the same moment. (4) Better look-alike handling without losing recall. (5) An optical model.
