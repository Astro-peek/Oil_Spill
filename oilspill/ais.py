"""Deliverable (c): reconstruct vessel traffic around the spill origin, filter it, score suspects.

AIS uses MarineCadastre-style columns. Synthetic traffic is provided for demonstrations only.

Scoring is deliberately a transparent weighted sum with the per-component breakdown returned, not a
black box: an attribution you cannot explain to a court or a port authority is not worth much.
"""
import math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

COLS = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName",
        "IMO", "CallSign", "VesselType", "Status", "Length", "Width", "Draft", "Cargo"]

R_LAT_M, R_LON_M = 110540.0, 111320.0


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def load_ais(path):
    """Validate CSV fixes; normalize timestamps to naive UTC for the internal pipeline."""
    df = pd.read_csv(path)
    required = {"MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"AIS CSV missing columns: {', '.join(sorted(missing))}")
    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"], utc=True, format="mixed", errors="coerce").dt.tz_localize(None)
    for col in required - {"BaseDateTime"}:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    valid = (df.BaseDateTime.notna() & df.LAT.between(-90, 90) & df.LON.between(-180, 180)
             & df.SOG.between(0, 102.2) & df.COG.ge(0) & df.COG.lt(360)
             & df.MMSI.between(100000000, 999999999) & df.MMSI.mod(1).eq(0))
    if not valid.all():
        raise ValueError(f"AIS CSV contains {int((~valid).sum())} invalid fixes (time, position, MMSI, SOG or COG)")
    df["MMSI"] = df.MMSI.astype("int64")
    if "VesselName" not in df:
        df["VesselName"] = df.MMSI.astype(str)
    df["VesselName"] = df.VesselName.fillna(df.MMSI.astype(str))
    return df.drop_duplicates(["MMSI", "BaseDateTime"], keep="last").sort_values(["MMSI", "BaseDateTime"])


def utc_time(value):
    return pd.to_datetime(value, utc=True).tz_localize(None)


def synth_traffic(origin_lon, origin_lat, when, n_vessels=40, hours=48, dt_min=10,
                  culprit_offset_h=31.0, seed=0, box_km=120.0, culprit_course=55.0):
    """Synthetic AIS for the spill region: background traffic plus one vessel that passes through
    the origin at the hindcast time and goes dark while doing it."""
    rng = np.random.default_rng(seed)
    t_end = utc_time(when)
    t_start = t_end - pd.Timedelta(hours=hours)
    rows = []
    dlat = box_km / (R_LAT_M / 1000)
    dlon = box_km / (R_LON_M * math.cos(math.radians(origin_lat)) / 1000)

    # Anchor each vessel at a random point near the spill at the RELEASE time and integrate both
    # ways, so traffic actually transits the incident area during the window. Seeding at t_start
    # instead makes every track radiate away and leaves the scene empty when it matters.
    t_anchor = t_end - pd.Timedelta(hours=culprit_offset_h)
    for v in range(n_vessels):
        mmsi = 200000000 + v
        course = rng.uniform(0, 360)
        sog = rng.uniform(8, 16)
        a_lat = origin_lat + rng.uniform(-dlat, dlat)
        a_lon = origin_lon + rng.uniform(-dlon, dlon)
        t = t_start
        while t <= t_end:
            dt_h = (t - t_anchor).total_seconds() / 3600.0
            km = sog * 1.852 * dt_h
            lat = a_lat + km * math.cos(math.radians(course)) / (R_LAT_M / 1000)
            lon = a_lon + km * math.sin(math.radians(course)) / (R_LON_M * math.cos(math.radians(a_lat)) / 1000)
            rows.append((mmsi, t, lat, lon, sog, course, course, f"VESSEL_{v:03d}",
                         9000000 + v, f"C{v:04d}", 70, 0, 180, 28, 9.5, 70))
            t += pd.Timedelta(minutes=dt_min)

    # the culprit: steams through the origin at t_end - culprit_offset_h, slows, and goes dark
    t_pass = t_end - pd.Timedelta(hours=culprit_offset_h)
    # a vessel discharging underway lays the slick ALONG its track, so the culprit's course should
    # match the slick's measured major-axis orientation
    course = culprit_course
    mmsi = 999000001
    t = t_start
    while t <= t_end:
        dt_h = (t - t_pass).total_seconds() / 3600.0
        sog = 6.0 if abs(dt_h) < 1.5 else 12.0          # slows down to discharge
        km = sog * 1.852 * dt_h
        lat = origin_lat + km * math.cos(math.radians(course)) / (R_LAT_M / 1000)
        lon = origin_lon + km * math.sin(math.radians(course)) / (R_LON_M * math.cos(math.radians(origin_lat)) / 1000)
        dark = abs(dt_h) < 1.0                          # transponder off across the discharge
        if not dark:
            rows.append((mmsi, t, lat, lon, sog, course, course, "SUSPECT_A",
                         9111111, "SUSA", 80, 0, 240, 40, 12.0, 80))
        t += pd.Timedelta(minutes=dt_min)

    return pd.DataFrame(rows, columns=COLS)


def interp_track(g, lo, hi, step="5min", max_gap_h=6.0):
    """Interpolate between exact fixes, with circular courses and no endpoint extrapolation."""
    gi = g.drop_duplicates("BaseDateTime", keep="last").set_index("BaseDateTime")[
        ["LON", "LAT", "COG", "SOG"]].sort_index().copy()
    if gi.empty:
        return gi
    gi["COG"] = np.degrees(np.unwrap(np.radians(gi.COG.to_numpy())))
    gi["LON"] = np.degrees(np.unwrap(np.radians(gi.LON.to_numpy())))
    grid = pd.date_range(max(lo, gi.index.min()), min(hi, gi.index.max()), freq=step)
    observed_index = gi.index
    gi = gi.reindex(gi.index.union(grid)).interpolate("time", limit_area="inside").loc[lo:hi]
    # Long reception gaps do not justify a precise inferred route. Keep actual fixes only.
    for left, right in zip(observed_index[:-1], observed_index[1:]):
        if (right-left).total_seconds() > max_gap_h*3600:
            gi = gi.loc[~((gi.index > left) & (gi.index < right))]
    gi["COG"] %= 360
    gi["LON"] = (gi.LON + 180) % 360 - 180
    return gi


def filter_traffic(df, origin_lon, origin_lat, when, hours_back, radius_km=60.0, pad_h=6.0):
    """Drop irrelevant traffic: keep only vessels near the origin during the release window.

    Distance is measured on the gap-interpolated track. Using raw fixes would discard precisely the
    vessels that switched their transponder off over the discharge — the prime suspects."""
    t_origin = utc_time(when) - pd.Timedelta(hours=hours_back)
    lo, hi = t_origin - pd.Timedelta(hours=pad_h), t_origin + pd.Timedelta(hours=pad_h)
    # Retain each vessel's real bracketing fixes even for narrow search windows.
    span = df
    keep = []
    for mmsi, g in span.groupby("MMSI"):
        gi = interp_track(g.sort_values("BaseDateTime"), lo, hi)
        if gi.empty:
            continue
        if haversine_km(gi.LON.values, gi.LAT.values, origin_lon, origin_lat).min() <= radius_km:
            keep.append(mmsi)
    return df[df.MMSI.isin(keep)].copy(), (lo, hi, t_origin)


def _angdiff180(a, b):
    return abs((a - b + 90) % 180 - 90)


def score_vessels(df, origin_lon, origin_lat, when, hours_back, slick_orientation_deg,
                  radius_km=60.0, pad_h=6.0, gap_min=45.0):
    """Score every vessel 0-100 on proximity, timing, track alignment and behavioural anomalies."""
    cand, (lo, hi, t_origin) = filter_traffic(df, origin_lon, origin_lat, when, hours_back,
                                              radius_km, pad_h)
    out = []
    for mmsi, g in cand.groupby("MMSI"):
        g = g.sort_values("BaseDateTime")
        win = (g.BaseDateTime >= lo) & (g.BaseDateTime <= hi)
        # CPA on a gap-INTERPOLATED track. A vessel that switches its transponder off over the
        # discharge has no fix at the origin, so raw CPA would report it as far away — exactly the
        # wrong conclusion. Interpolating across silence is what an investigator does by hand.
        gi = interp_track(g, lo, hi)
        if gi.empty:
            continue
        d_win = haversine_km(gi.LON.values, gi.LAT.values, origin_lon, origin_lat)
        cpa = float(d_win.min())                                  # closest point of approach
        i_cpa = int(np.argmin(d_win))
        t_cpa = gi.index[i_cpa]
        dt_h = abs((pd.Timestamp(t_cpa) - t_origin).total_seconds()) / 3600.0
        cpa_observed = (float(haversine_km(g.LON.values[win.values], g.LAT.values[win.values],
                                          origin_lon, origin_lat).min()) if win.any() else None)

        # behavioural: AIS silence overlapping the window
        gaps = g.BaseDateTime.diff().dt.total_seconds().div(60).fillna(0)
        previous = g.BaseDateTime.shift()
        overlaps = (previous < hi) & (g.BaseDateTime > lo)
        gap_len = float(gaps[overlaps].max()) if overlaps.any() else 0.0
        covers = (previous <= t_origin) & (g.BaseDateTime >= t_origin) & (gaps >= gap_min)
        gap_covers = bool(covers.any())
        origin_gap = float(gaps[covers].max()) if gap_covers else 0.0

        sog = g.SOG.values
        slow = float(np.median(sog)) - float(np.min(sog[win.values])) if win.any() else 0.0
        cog_cpa = float(gi.COG.values[i_cpa])
        align = _angdiff180(cog_cpa, slick_orientation_deg)       # 0 = track along slick axis

        c = {
            "proximity":   math.exp(-cpa / 15.0),                       # 15 km e-folding
            "timing":      math.exp(-dt_h / 3.0),                       # 3 h e-folding
            "alignment":   max(0.0, 1.0 - align / 90.0),
            "dark_gap":    1.0 if gap_covers else min(gap_len / (4 * gap_min), 0.5),
            "speed_drop":  min(max(slow, 0.0) / 6.0, 1.0),
        }
        w = {"proximity": 0.30, "timing": 0.20, "alignment": 0.15, "dark_gap": 0.25, "speed_drop": 0.10}
        score = 100.0 * sum(w[k] * c[k] for k in w)
        out.append({
            "MMSI": int(mmsi), "VesselName": str(g.VesselName.iloc[0]),
            "score": round(score, 2), "cpa_km": round(cpa, 2),
            "cpa_km_observed": round(cpa_observed, 2) if cpa_observed is not None else None,
            "cpa_time": pd.Timestamp(t_cpa).isoformat() + "Z",
            "cpa_hours_before_acquisition": round((utc_time(when) - t_cpa).total_seconds() / 3600, 2),
            "dt_hours": round(dt_h, 2),
            "cog_at_cpa": round(cog_cpa, 1), "align_deg": round(align, 1),
            "max_gap_min": round(gap_len, 1), "gap_covers_origin": bool(gap_covers),
            "origin_gap_min": round(origin_gap, 1),
            "speed_drop_kn": round(slow, 2),
            "components": {k: round(v, 3) for k, v in c.items()},
        })
    return sorted(out, key=lambda r: -r["score"])

