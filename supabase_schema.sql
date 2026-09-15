-- ============================================================
-- OceanTrace — Supabase (Postgres + PostGIS) schema
-- Run in the Supabase SQL editor, top to bottom.
-- ============================================================

create extension if not exists postgis;
create extension if not exists "uuid-ossp";

-- ------------------------------------------------------------
-- investigations
-- ------------------------------------------------------------
create table if not exists investigations (
  id               uuid primary key default uuid_generate_v4(),
  code             text unique not null,               -- e.g. OT-2026-0913-001
  lat              double precision not null,
  lon              double precision not null,
  location         geometry(Point, 4326) generated always as (st_setsrid(st_makepoint(lon, lat), 4326)) stored,
  environment      jsonb not null default '{"windSpeed":12,"windDir":45,"currentSpeed":0.8,"currentDir":30}',
  what_if          jsonb not null default '{"radiusKm":8.5,"timeShiftHours":0}',
  origin_lat       double precision,
  origin_lon       double precision,
  origin_radius_km double precision,
  status           text not null default 'created',    -- created | analyzing | complete
  created_by       uuid references auth.users(id),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index if not exists idx_investigations_location on investigations using gist (location);

-- ------------------------------------------------------------
-- satellite_scenes
-- ------------------------------------------------------------
create table if not exists satellite_scenes (
  id               uuid primary key default uuid_generate_v4(),
  investigation_id uuid not null references investigations(id) on delete cascade,
  sensor           text default 'Sentinel-1 SAR C-Band',
  storage_path     text not null,
  public_url       text,
  uploaded_at      timestamptz not null default now()
);
create index if not exists idx_scenes_investigation on satellite_scenes(investigation_id);

-- ------------------------------------------------------------
-- detections (AI segmentation output)
-- ------------------------------------------------------------
create table if not exists detections (
  id                 uuid primary key default uuid_generate_v4(),
  investigation_id   uuid not null references investigations(id) on delete cascade,
  scene_id           uuid references satellite_scenes(id) on delete set null,
  confidence         double precision not null,
  area_sqkm          double precision not null,
  centroid           geometry(Point, 4326) not null,
  slick_age_hours    double precision,
  look_alike_risk    boolean not null default false,
  polygon            geometry(Polygon, 4326),
  created_at         timestamptz not null default now()
);
create index if not exists idx_detections_investigation on detections(investigation_id);
create index if not exists idx_detections_centroid on detections using gist (centroid);
create index if not exists idx_detections_polygon on detections using gist (polygon);

-- ------------------------------------------------------------
-- drift_results (back-drift + forward forecast)
-- ------------------------------------------------------------
create table if not exists drift_results (
  id                 uuid primary key default uuid_generate_v4(),
  investigation_id   uuid not null references investigations(id) on delete cascade,
  trajectory_back    jsonb not null,     -- array of [lat, lon]
  trajectory_forward jsonb not null,     -- array of [lat, lon]
  uncertainty_cone   jsonb,              -- array of [lat, lon]
  origin_lat         double precision not null,
  origin_lon         double precision not null,
  origin_radius_km   double precision not null,
  created_at         timestamptz not null default now()
);
create index if not exists idx_drift_investigation on drift_results(investigation_id);

-- ------------------------------------------------------------
-- vessels (reference registry — seed with demo data, extend later)
-- ------------------------------------------------------------
create table if not exists vessels (
  mmsi               bigint primary key,
  imo                text,
  name               text not null,
  vessel_type        text,          -- tanker / cargo / infrastructure / uncertain
  flag_country       text,
  deadweight_tonnage double precision,
  length_meters      double precision
);

insert into vessels (mmsi, name, vessel_type, flag_country)
values
  (235001234, 'Candidate Vessel A', 'tanker', 'UK'),
  (353109876, 'Candidate Vessel B', 'cargo', 'Panama'),
  (412356789, 'Candidate Vessel C', 'tanker', 'China')
on conflict (mmsi) do nothing;

-- ------------------------------------------------------------
-- investigation_suspects (ranked candidates per investigation)
-- ------------------------------------------------------------
create table if not exists investigation_suspects (
  id                uuid primary key default uuid_generate_v4(),
  investigation_id  uuid not null references investigations(id) on delete cascade,
  mmsi              bigint references vessels(mmsi),
  name_snapshot     text not null,
  source_type       text not null default 'vessel',   -- vessel | infrastructure | uncertain
  sog               text,
  cog               text,
  dist_km           double precision,
  time_match        text,                              -- High | Medium | Low
  base_score        double precision,
  score             double precision,
  ais_gap_flag      boolean not null default false,
  reasons           jsonb default '[]',
  lowering_factors  jsonb default '[]',
  track_points      jsonb,                             -- array of [lat, lon]
  rank              int,
  status            text default 'under_investigation',-- under_investigation | cleared | accused
  created_at        timestamptz not null default now()
);
create index if not exists idx_suspects_investigation on investigation_suspects(investigation_id);
create index if not exists idx_suspects_mmsi on investigation_suspects(mmsi);

-- ------------------------------------------------------------
-- evidence_events (timeline shown in Evidence Chain UI)
-- ------------------------------------------------------------
create table if not exists evidence_events (
  id                uuid primary key default uuid_generate_v4(),
  investigation_id  uuid not null references investigations(id) on delete cascade,
  event_type        text not null,      -- success | warning
  occurred_label    text not null,      -- e.g. "T - 36h"
  title             text not null,
  description       text not null,
  source            text,
  created_at        timestamptz not null default now()
);
create index if not exists idx_events_investigation on evidence_events(investigation_id);

-- ------------------------------------------------------------
-- dossiers (generated PDF metadata)
-- ------------------------------------------------------------
create table if not exists dossiers (
  id                uuid primary key default uuid_generate_v4(),
  investigation_id  uuid not null references investigations(id) on delete cascade,
  storage_path      text not null,
  generated_by      uuid references auth.users(id),
  generated_at      timestamptz not null default now()
);
create index if not exists idx_dossiers_investigation on dossiers(investigation_id);

-- ============================================================
-- Row Level Security
-- Hackathon-simple policy: any authenticated user has the
-- "investigator" role. No anonymous writes, ever.
-- ============================================================

alter table investigations         enable row level security;
alter table satellite_scenes       enable row level security;
alter table detections             enable row level security;
alter table drift_results          enable row level security;
alter table vessels                enable row level security;
alter table investigation_suspects enable row level security;
alter table evidence_events        enable row level security;
alter table dossiers               enable row level security;

-- Authenticated users: full read/write on investigation data
create policy "investigators_full_access_investigations"
  on investigations for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "investigators_full_access_scenes"
  on satellite_scenes for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "investigators_full_access_detections"
  on detections for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "investigators_full_access_drift"
  on drift_results for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "investigators_read_vessels"
  on vessels for select
  using (auth.role() = 'authenticated');

create policy "investigators_full_access_suspects"
  on investigation_suspects for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "investigators_full_access_events"
  on evidence_events for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "investigators_full_access_dossiers"
  on dossiers for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

-- ============================================================
-- Storage buckets (run via Supabase dashboard or storage API,
-- included here for reference — SQL editor cannot create
-- buckets directly in all Supabase versions):
--   satellite-scenes  (private)
--   dossiers          (private, access via signed URLs only)
-- ============================================================
