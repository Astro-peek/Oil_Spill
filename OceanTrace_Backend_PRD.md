# OceanTrace — Backend & Supabase Integration PRD
**Team OceanSentinel · SIH 2026 · Problem Statement 26143**

| | |
|---|---|
| Document type | Product/Engineering Requirements Document (backend phase) |
| Status | Ready for implementation |
| Audience | Backend engineer / autonomous dev agent (ADE) |
| Depends on | Existing frontend (`OCEANTRACE-main.zip` — index.html / script.js / style.css) |
| Excludes | The AI/ML model itself (segmentation, drift physics, attribution scoring) — being built separately by a teammate. This PRD defines the **contract** that model must satisfy and ships a **mock service** that fulfills that contract today, so the rest of the system is fully working and swappable later. |

---

## 1. Current State (as found in the uploaded repo)

The frontend is a static site (`index.html`, `script.js`, `style.css`, Leaflet for maps) that is **fully self-contained and 100% simulated on the client**:

- `script.js` already declares backend-ready stubs it never calls:
  ```js
  const CONFIG = {
    API_BASE_URL: 'https://api.oceantrace.example.com/v1',
    ENDPOINTS: {
      UPLOAD: '/api/detection/upload',
      DETECT: '/api/detection/segment',
      VALIDATE: '/api/validation/lookalike',
      DRIFT: '/api/drift/lagrangian',
      AIS_CORRELATE: '/api/ais/correlate',
      ATTRIBUTION: '/api/vessel/attribution',
      DOSSIER: '/api/evidence/dossier'
    }
  };
  ```
- All "detection", drift trajectories, vessel candidates, scores, and the evidence dossier are computed by deterministic JS functions in the browser (`calculateDriftTrajectory`, `generateVesselsAroundOrigin`, `recalculateVesselScores`, `generateDossier`, `exportDossierReport`) — nothing is persisted, nothing survives a page refresh, and the "export" button just downloads a client-generated `.txt` blob.
- There is no auth, no database, no file storage, no real AI call anywhere in the code.

**Implication for this PRD:** the backend's job is to (a) stand up Supabase as the real data/storage layer, (b) stand up an API layer that reproduces — then later replaces — the logic currently faked in `script.js`, and (c) make the smallest possible changes to the existing frontend so it calls real endpoints instead of local math.

---

## 2. Scope

**In scope (this phase / this document):**
- Supabase project: Postgres + PostGIS schema, Storage buckets, Auth, Realtime, RLS
- Node.js/Express API layer implementing every endpoint the frontend needs
- A **mock analysis engine** that ports the existing drift/scoring math from `script.js` to the server, so the app is fully functional end-to-end today
- A clean, versioned **AI service contract** (request/response schema) so your friend's model can be dropped in later by only changing one config flag — zero frontend changes, zero schema changes
- Real PDF evidence dossier generation + storage (replacing the client-side `.txt` download)
- Minimal, surgical edits to `script.js` to call the real API instead of local mock functions

**Out of scope (not this document):**
- Training or serving the actual segmentation / drift-physics / attribution ML model (teammate's work)
- Ingesting live Sentinel-1/2, ERA5, CMEMS, or AISStream feeds (documented as a Phase 2 stretch goal, §11)
- Rebuilding the frontend in React/deck.gl (the research doc proposes this, but the existing HTML/JS/Leaflet frontend is done and works — do not rewrite it)

---

## 3. Architecture

```
┌──────────────────────┐        REST/JSON over HTTPS       ┌───────────────────────────┐
│   Frontend (as-is)    │ ─────────────────────────────────▶│  Backend API (Node/Express) │
│ index.html/script.js  │◀───────────────────────────────── │        api.oceantrace/*    │
│ Leaflet map           │        Supabase Realtime (WS)      └─────────────┬─────────────┘
└──────────────────────┘◀────────────────────────────────────────────────┘
                                                                            │
                                          ┌─────────────────────────────────┼─────────────────────────────┐
                                          ▼                                 ▼                             ▼
                              ┌───────────────────────┐      ┌─────────────────────────┐    ┌───────────────────────┐
                              │ Supabase Postgres      │      │ Supabase Storage         │    │ AI Service (teammate)  │
                              │ + PostGIS              │      │ (SAR images, PDFs)       │    │ FastAPI — plugged in   │
                              │ investigations, spills,│      │                          │    │ later via AI_SERVICE_  │
                              │ vessels, suspects...   │      │                          │    │ URL env var             │
                              └───────────────────────┘      └─────────────────────────┘    └───────────────────────┘
                                                                                                       ▲
                                                                                          Until ready: internal
                                                                                          MOCK engine fulfills the
                                                                                          same contract (§7)
```

**Why this shape:**
- Express sits between the frontend and Supabase so business rules (scoring, validation, orchestration) live in one place, not scattered across RLS policies or client JS.
- Supabase gives you Postgres+PostGIS (proper geospatial queries for "which vessels were within R km during window T"), file storage (SAR images + generated PDFs), auth, and realtime — all managed, no infra to run for a hackathon timeline.
- The AI model is accessed through **one internal interface** (`services/aiClient.js`). Today it's implemented by a mock that reproduces the current frontend math server-side. When your teammate's model is ready, you implement the same interface against their real endpoint and flip `AI_SERVICE_MODE=live` in `.env`. Nothing else changes.

---

## 4. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| API server | Node.js 20 LTS + Express | Matches the research doc; simple for an agent to scaffold and for you to debug |
| Database | Supabase Postgres 15 + PostGIS extension | Managed, geospatial-native |
| Storage | Supabase Storage | SAR image uploads, generated PDF dossiers |
| Auth | Supabase Auth (email/password or magic link) | One role for now: `investigator`. Public/anonymous read is optional (§9) |
| Realtime | Supabase Realtime (Postgres CDC) | Optional nice-to-have — push live updates to the dashboard (§11) |
| PDF generation | `pdfkit` (pure JS, no headless browser needed) | Simpler to deploy than Puppeteer for a hackathon judge demo |
| Validation | `zod` | Validate every request body before touching the DB |
| HTTP client (→ AI service later) | `axios` with timeout + retry | Used only inside `services/aiClient.js` |

---

## 5. Supabase Schema

Full SQL migration is provided as a separate file: **`supabase_schema.sql`**. Summary:

| Table | Purpose |
|---|---|
| `investigations` | One row per investigation (the `OT-2026-0913-001` ID). Holds coordinates, environment sliders, drift/what-if params, status. |
| `satellite_scenes` | Uploaded SAR/EO image metadata + Storage path, linked to an investigation. |
| `detections` | AI detection output: confidence, area, centroid, slick age, look-alike risk, polygon. |
| `drift_results` | Back-drift & forward-drift trajectories, origin zone, uncertainty cone — as GeoJSON. |
| `vessels` | Reference table of known vessels (MMSI, name, type, flag) — seed with the 3-4 demo vessels; real data can be loaded later. |
| `investigation_suspects` | Ranked candidate vessels per investigation: scores, distance, reasons, AIS-gap flag. |
| `evidence_events` | Timeline entries shown in the Evidence Chain UI. |
| `dossiers` | Generated PDF metadata + Storage path + signed URL. |

Key PostGIS features used:
- `geometry(Point, 4326)` / `geometry(Polygon, 4326)` / `geometry(LineString, 4326)` columns for centroid, slick polygon, drift lines.
- `ST_DWithin(geom, point, radius_m)` for "vessels within R km of origin" once real AIS data exists.
- GIST indexes on every geometry column.

---

## 6. API Contract

Base path: `/api/v1`. All bodies are JSON. All responses follow:
```json
{ "success": true, "data": { ... } }
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "..." } }
```

### 6.1 `POST /investigations`
Create a new investigation (mirrors `generateNewInvestigationId()` + initial state in `script.js`).

Request:
```json
{ "lat": 19.0760, "lon": 72.8777 }
```
Response:
```json
{
  "id": "uuid",
  "code": "OT-2026-0913-001",
  "coordinates": { "lat": 19.0760, "lon": 72.8777 },
  "environment": { "windSpeed": 12, "windDir": 45, "currentSpeed": 0.8, "currentDir": 30 },
  "whatIf": { "radiusKm": 8.5, "timeShiftHours": 0 },
  "status": "created",
  "createdAt": "2026-09-13T10:00:00Z"
}
```

### 6.2 `GET /investigations/:id`
Returns the full current state (detection, drift, vessels, evidence, dossier if present) — used on page load/refresh so state survives, unlike today's pure-client version.

### 6.3 `PATCH /investigations/:id`
Partial update for location / environment sliders / what-if params (mirrors `updateInvestigationLocation`, wind/current sliders, `radiusSlider`/`timeShiftSlider`).

Request (any subset):
```json
{
  "coordinates": { "lat": 19.10, "lon": 72.90 },
  "environment": { "windSpeed": 18, "windDir": 90 },
  "whatIf": { "radiusKm": 12, "timeShiftHours": -4 }
}
```
Response: updated investigation object. If `coordinates` or `environment` changed, the backend automatically recomputes drift + vessel scores server-side (equivalent to `recalculatePhysicsAndRender()`) and includes the fresh `drift` and `vessels` in the response — the frontend just re-renders instead of recalculating.

### 6.4 `POST /investigations/:id/upload`
Multipart upload of the SAR/EO image (mirrors `handleFile`/`loadSampleImage`). Stores the file in Supabase Storage bucket `satellite-scenes`, inserts a `satellite_scenes` row.

Response:
```json
{ "sceneId": "uuid", "storagePath": "satellite-scenes/OT-2026-0913-001/scene1.tiff", "publicUrl": "..." }
```

### 6.5 `POST /investigations/:id/analyze`
The main orchestration endpoint. Runs the full pipeline in order and persists every step (mirrors the `runBtn` click handler and its 6-step animated pipeline):

1. `detect` — call AI service contract §7.1 → insert `detections` row
2. `validate` — look-alike risk check
3. `drift` — call AI service contract §7.2 → insert `drift_results` row, update `investigations.origin_*`
4. `correlate` — call AI service contract §7.3 → candidate vessels
5. `attribute` — score & rank candidates → insert `investigation_suspects` rows
6. `evidence` — build the evidence chain → insert `evidence_events` rows

Request:
```json
{ "sceneId": "uuid" }
```
Response: the complete result bundle — `detection`, `drift`, `vessels[]`, `evidenceChain[]` — in the exact shape the frontend already expects from `appState`, so `completeAnalysis()` in `script.js` needs almost no changes.

### 6.6 `POST /investigations/:id/dossier/export`
Generates the legal evidence PDF (replaces `exportDossierReport()`'s client-side `.txt` blob), uploads it to the `dossiers` Storage bucket, returns a signed URL.

Response:
```json
{ "dossierId": "uuid", "downloadUrl": "https://.../signed-url", "expiresAt": "2026-09-13T11:00:00Z" }
```

### 6.7 `GET /vessels/:mmsi`
Optional vessel registry lookup (static/demo data for now; real AIS integration later).

---

## 7. AI Service Contract (the interface your teammate's model must satisfy)

This is the most important section for parallel work. Your teammate can build and test their model completely independently as long as they return these shapes. Until their service exists, `services/aiClient.js` is implemented by an internal mock (`services/mock/analysisEngine.js`) that ports the exact math already in `script.js` (`calculateDriftTrajectory`, `calculateUncertaintyCone`, `generateVesselsAroundOrigin`, `recalculateVesselScores`) so behavior is identical to the current demo.

Toggle in `.env`:
```
AI_SERVICE_MODE=mock      # or "live"
AI_SERVICE_URL=https://your-teammates-fastapi-service/...
AI_SERVICE_TIMEOUT_MS=15000
```

### 7.1 Detection — `POST {AI_SERVICE_URL}/predict/spill-segmentation`
Request:
```json
{ "imageUrl": "https://.../scene1.tiff", "lat": 19.0760, "lon": 72.8777 }
```
Response (must match):
```json
{
  "confidence": 87,
  "areaKm2": 14.8,
  "centroid": { "lat": 19.0812, "lon": 72.8547 },
  "slickAgeHours": 24,
  "lookAlikeRisk": false,
  "polygon": { "type": "Polygon", "coordinates": [[[lon,lat], ...]] }
}
```

### 7.2 Drift — `POST {AI_SERVICE_URL}/predict/drift-trajectory`
Request:
```json
{
  "centroid": { "lat": 19.0812, "lon": 72.8547 },
  "slickAgeHours": 24,
  "environment": { "windSpeed": 12, "windDir": 45, "currentSpeed": 0.8, "currentDir": 30 },
  "forecastHours": 48
}
```
Response (must match):
```json
{
  "trajectoryBack": [[lat, lon], ...],
  "trajectoryForward": [[lat, lon], ...],
  "origin": { "lat": 19.0120, "lon": 72.7800, "radiusKm": 8.5 },
  "uncertaintyCone": [[lat, lon], ...]
}
```

### 7.3 AIS Correlation & Attribution — `POST {AI_SERVICE_URL}/attribution/rank-suspects`
Request:
```json
{
  "origin": { "lat": 19.0120, "lon": 72.7800, "radiusKm": 8.5 },
  "releaseWindow": { "start": "2026-09-12T00:00:00Z", "end": "2026-09-12T18:00:00Z" },
  "whatIf": { "radiusKm": 8.5, "timeShiftHours": 0 }
}
```
Response (must match, array sorted by score desc):
```json
[
  {
    "mmsi": "235001234",
    "name": "Candidate Vessel A",
    "type": "vessel",
    "sog": "12.4 kts",
    "cog": "045°",
    "distKm": 3.4,
    "timeMatch": "High",
    "score": 87,
    "trackPoints": [[lat, lon], ...],
    "reasons": ["Close to estimated origin zone centroid", "..."],
    "lowering": ["Speed anomaly detected 2h prior to release"],
    "anomaly": false
  }
]
```

**Whoever owns the AI service just needs to return JSON in these three shapes — everything downstream (DB writes, scoring persistence, PDF generation, frontend rendering) is already built against this contract and won't need to change.**

---

## 8. Frontend Integration — exact edits needed to `script.js`

The frontend does **not** need a rewrite. Replace only these functions with `fetch()` calls to the endpoints above; keep every DOM/render function (`renderMapLayers`, `renderVesselsTable`, `showVesselDetail`, etc.) as-is since they just read from `appState`:

| Existing function | Replace with |
|---|---|
| App boot | `POST /investigations` on first load (or `GET /investigations/:id` if resuming via URL param) |
| `updateInvestigationLocation()` | `PATCH /investigations/:id` with new coordinates, then set `appState` from the response |
| Wind/current slider `input` handlers | Debounced `PATCH /investigations/:id` with new `environment` |
| `radiusSlider` / `timeShiftSlider` handlers | Debounced `PATCH /investigations/:id` with new `whatIf` |
| `handleFile()` / `loadSampleImage()` | `POST /investigations/:id/upload`, store returned `sceneId` |
| `initAnalysis()` click handler | `POST /investigations/:id/analyze` (keep the same animated step UI — just await the real call instead of `setTimeout`) |
| `generateVesselsAroundOrigin()` / `recalculateVesselScores()` | Delete — server now returns `vessels[]` directly |
| `calculateDriftTrajectory()` / `calculateUncertaintyCone()` | Delete — server now returns `drift` directly |
| `generateEvidenceChain()` | Delete — server now returns `evidenceChain[]` directly |
| `exportDossierReport()` | `POST /investigations/:id/dossier/export`, then `window.location = downloadUrl` |
| `CONFIG.API_BASE_URL` | Point at your real deployed backend URL |

This keeps the diff small and low-risk — ideal for an ADE to execute mechanically.

---

## 9. Auth & Security

- Supabase Auth, single role for the hackathon: `investigator` (email/password is enough — no need for magic links or SSO).
- RLS enabled on every table. Policy for the demo timeline: authenticated `investigator` users get full read/write; there is **no public/anonymous write** under any circumstance.
- Judges/public demo viewing: expose a read-only, sanitized view (`public_investigations_view`) that hides MMSI numbers and exact vessel names if you want a "public transparency" mode later — not required for the hackathon demo itself.
- All secrets (`SUPABASE_SERVICE_ROLE_KEY`, `AI_SERVICE_URL`, future Copernicus/AISStream keys) go in `.env`, never committed. Provide `.env.example` with empty values.
- Validate every request body with `zod` before it touches Supabase — reject malformed lat/lon, out-of-range sliders, oversized uploads.
- Rate-limit `/analyze` and `/upload` (e.g. `express-rate-limit`) since they're the most expensive calls.

---

## 10. Environment Variables

```
# Server
PORT=4000
NODE_ENV=development

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET_SCENES=satellite-scenes
SUPABASE_STORAGE_BUCKET_DOSSIERS=dossiers

# AI Service
AI_SERVICE_MODE=mock
AI_SERVICE_URL=
AI_SERVICE_TIMEOUT_MS=15000

# Misc
CORS_ORIGIN=http://localhost:5500
```

---

## 11. Phase 2 / Stretch Goals (explicitly not required for the hackathon deadline)

- Swap `AI_SERVICE_MODE=live` once your teammate's FastAPI model is ready — no other code changes needed if they honor §7.
- Ingest real Sentinel-1/2 (Copernicus), ERA5 wind, CMEMS currents, and AISStream.io feeds via a scheduled job (BullMQ or a simple cron) instead of manual upload.
- Supabase Realtime channel so multiple investigators see the same investigation update live.
- Replace demo `vessels` table with a real MMSI/IMO registry.
- Signed, tamper-evident PDF (checksum + timestamp) for genuine legal chain-of-custody.

---

## 12. Implementation Checklist (for the ADE — execute top to bottom)

- [ ] Create Supabase project; enable the `postgis` extension
- [ ] Run `supabase_schema.sql` (tables, indexes, RLS policies)
- [ ] Create Storage buckets: `satellite-scenes` (private), `dossiers` (private, signed-URL access)
- [ ] Scaffold Express app per the folder structure in §4/§13; wire `.env` from §10
- [ ] Implement `services/mock/analysisEngine.js` by porting `calculateDriftTrajectory`, `calculateUncertaintyCone`, `generateVesselsAroundOrigin`, `recalculateVesselScores` from `script.js` into server-side JS (same math, same output shapes)
- [ ] Implement `services/aiClient.js` with `mode = mock | live` switch per §7
- [ ] Implement all endpoints in §6, each writing to the correct table(s) from §5
- [ ] Implement `services/dossier.js` using `pdfkit`, upload to `dossiers` bucket, return signed URL
- [ ] Add `zod` request validation + centralized error handler + `express-rate-limit`
- [ ] Add Supabase Auth middleware (`investigator` role required on all write routes)
- [ ] Edit `script.js` per the exact mapping in §8 — no other frontend files should need changes
- [ ] Smoke test: create investigation → upload sample image → run analysis → confirm map, vessel table, and dossier all populate from server data → export PDF → refresh page and confirm state reloads from `GET /investigations/:id`
- [ ] Deploy backend (Render/Railway/Fly.io all fine); update `CONFIG.API_BASE_URL` in `script.js` to the deployed URL; update `CORS_ORIGIN`

## 13. Suggested Backend Repo Structure

```
backend/
  src/
    config/
      env.js
      supabase.js
    routes/
      investigations.routes.js
      vessels.routes.js
    controllers/
      investigations.controller.js
      vessels.controller.js
    services/
      aiClient.js
      dossier.js
      mock/
        analysisEngine.js
    middleware/
      auth.js
      validate.js
      errorHandler.js
      rateLimit.js
    schemas/
      investigation.schema.js
    app.js
    server.js
  .env.example
  package.json
supabase_schema.sql
```

## 14. Definition of Done

The hackathon demo works end-to-end with the *existing* frontend UI, unchanged in look and feel, but every number on screen is real: created and persisted in Supabase, survives a page refresh, and the exported dossier is a real downloadable PDF pulled from Storage rather than a client-generated text blob. Swapping in the real AI model later requires touching only `AI_SERVICE_MODE`/`AI_SERVICE_URL` and the `live` implementation of `aiClient.js` — nothing in the schema, routes, or frontend.
