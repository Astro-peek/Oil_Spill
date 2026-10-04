"""Deliverable (b): Lagrangian slick drift — forward forecast and backward hindcast to origin.

Physics: a surface slick moves with the ocean current plus a fraction of the wind ("windage",
~3% of wind speed for oil), with turbulent spreading modelled as a random walk.

    drift = current + windage * wind        (optionally deflected by Coriolis)

Backtracking subtlety worth understanding before trusting the output: under a SPATIALLY UNIFORM
field, reversing time just translates the particle cloud rigidly — it never contracts, so no origin
time can be recovered. Convergence requires velocity shear, and more importantly the physical fact
that a discharging vessel lays down a LINE source as it steams. So the origin is estimated as a
line and a time WINDOW, not a point, which is also what the problem statement asks for
("reconstruct vessel traffic around the origin window in space and time").
"""
import math
import numpy as np

R_LAT_M = 110540.0      # metres per degree latitude
R_LON_M = 111320.0      # metres per degree longitude at the equator


def m_per_deg_lon(lat):
    return R_LON_M * np.cos(np.radians(lat))


class UniformField:
    """Constant (u, v) everywhere — the null case, and the one where origin TIME is unrecoverable."""
    def __init__(self, u, v):
        self.u, self.v = u, v

    def __call__(self, lon, lat, t):
        return np.full_like(np.asarray(lon, float), self.u), np.full_like(np.asarray(lat, float), self.v)


class ShearField:
    """u varies linearly with latitude: du/dy = shear (1/s). Gives a cloud something to converge from."""
    def __init__(self, u0, v0, shear, lat0):
        self.u0, self.v0, self.shear, self.lat0 = u0, v0, shear, lat0

    def __call__(self, lon, lat, t):
        dy = (np.asarray(lat, float) - self.lat0) * R_LAT_M
        return self.u0 + self.shear * dy, np.full_like(np.asarray(lat, float), self.v0)


class DriftField:
    """current + windage*wind, with optional deflection to the right (N. hemisphere Coriolis)."""
    def __init__(self, current=None, wind=None, windage=0.03, deflection_deg=0.0):
        self.current, self.wind = current, wind
        self.windage, self.defl = windage, math.radians(deflection_deg)

    def __call__(self, lon, lat, t):
        u = np.zeros_like(np.asarray(lon, float))
        v = np.zeros_like(u)
        if self.current is not None:
            cu, cv = self.current(lon, lat, t)
            u, v = u + cu, v + cv
        if self.wind is not None:
            wu, wv = self.wind(lon, lat, t)
            if self.defl:
                c, s = math.cos(self.defl), math.sin(self.defl)
                wu, wv = c * wu + s * wv, -s * wu + c * wv
            u, v = u + self.windage * wu, v + self.windage * wv
        return u, v


def _step(lon, lat, field, t, dt):
    """One RK2 (midpoint) advection step. dt in seconds, may be negative for hindcast."""
    u1, v1 = field(lon, lat, t)
    lon_m = lon + (u1 * dt / 2) / m_per_deg_lon(lat)
    lat_m = lat + (v1 * dt / 2) / R_LAT_M
    u2, v2 = field(lon_m, lat_m, t + dt / 2)
    return (lon + (u2 * dt) / m_per_deg_lon(lat_m),
            lat + (v2 * dt) / R_LAT_M)


def advect(lon0, lat0, field, hours, dt_s=900.0, diffusivity=0.0, seed=0, t0=0.0):
    """Advect particles for `hours` (negative = backward). Returns (times_s, lons, lats) with
    shape (nsteps+1, nparticles). `diffusivity` is horizontal eddy diffusivity in m^2/s."""
    lon = np.asarray(lon0, float).copy()
    lat = np.asarray(lat0, float).copy()
    if (lon.ndim != 1 or lon.shape != lat.shape or lon.size == 0
            or not np.isfinite(lon).all() or not np.isfinite(lat).all()
            or np.any(np.abs(lat) >= 89)):
        raise ValueError("Particles must be finite, paired 1D coordinates below 89 degrees latitude")
    if not all(math.isfinite(v) for v in [hours, dt_s, diffusivity, t0]) or dt_s <= 0 or diffusivity < 0:
        raise ValueError("Finite duration, positive dt_s and nonnegative diffusivity required")
    total = abs(hours) * 3600.0
    dt = math.copysign(dt_s, hours)
    n = int(math.ceil(total / dt_s))
    rng = np.random.default_rng(seed)

    ts = np.empty(n + 1)
    L = np.empty((n + 1, lon.size))
    A = np.empty((n + 1, lat.size))
    ts[0], L[0], A[0] = t0, lon, lat
    t = t0
    for i in range(1, n + 1):
        dt = math.copysign(min(dt_s, total - (i - 1) * dt_s), hours)
        lon, lat = _step(lon, lat, field, t, dt)
        if not np.isfinite(lon).all() or not np.isfinite(lat).all() or np.any(np.abs(lat) >= 89):
            raise ValueError("Drift left the supported coordinate domain")
        if diffusivity > 0:
            s = math.sqrt(2 * diffusivity * abs(dt))
            lon = lon + rng.normal(0, s, lon.shape) / m_per_deg_lon(lat)
            lat = lat + rng.normal(0, s, lat.shape) / R_LAT_M
        t += dt
        ts[i], L[i], A[i] = t, lon, lat
    return ts, L, A


def spread_m(lons, lats):
    """RMS distance of particles from their centroid, in metres — the cloud's size."""
    lat0 = lats.mean()
    x = (lons - lons.mean()) * m_per_deg_lon(lat0)
    y = (lats - lats.mean()) * R_LAT_M
    return float(np.sqrt(np.mean(x * x + y * y)))


def minor_spread_m(lons, lats):
    """RMS width across the cloud's SHORT axis. A line source collapses in this, not in `spread_m`."""
    lat0 = lats.mean()
    x = (lons - lons.mean()) * m_per_deg_lon(lat0)
    y = (lats - lats.mean()) * R_LAT_M
    pts = np.stack([x, y], 1)
    if len(pts) < 3:
        return 0.0
    _, s, _ = np.linalg.svd(pts - pts.mean(0), full_matrices=False)
    return float(s[-1] / math.sqrt(len(pts)))


def hindcast_origin(lons, lats, field, max_hours=48, dt_s=900.0, criterion="minor"):
    """Backtrack the slick and find the release time — the point where it was most compact.

    `criterion` must match the release geometry, and choosing wrong gives a meaningless answer:
      "minor" — a vessel discharging while underway lays a LINE. Its across-track width collapses
                at release, while its along-track length does not. This is the default because it
                is the case the problem statement cares about.
      "total" — a stationary point release (grounding, blowout, single dump). Overall spread
                collapses at release.

    Neither can work under a spatially uniform field: reversing a rigid translation never contracts
    anything. Always check `contraction_ratio` — near 1.0 means the field carried no information
    and the reported time is not meaningful.

    Check `time_resolved` too: False means the spread was still shrinking at max_hours, so
    `hours_back` is just the search limit. `origin_lon/lat` can still be usable in that case."""
    if criterion not in {"minor", "total"} or max_hours <= 0:
        raise ValueError("Positive max_hours and criterion minor or total required")
    ts, L, A = advect(lons, lats, field, -abs(max_hours), dt_s=dt_s)
    minor = np.array([minor_spread_m(L[i], A[i]) for i in range(len(ts))])
    total = np.array([spread_m(L[i], A[i]) for i in range(len(ts))])
    curve = minor if criterion == "minor" else total
    k = int(np.argmin(curve))
    # A minimum sitting on the search boundary is not a minimum: under a purely divergent field the
    # cloud keeps contracting the further back you go, so argmin just lands on max_hours. The
    # location is still meaningful, the TIME is not. Say so rather than returning a boundary value.
    time_resolved = 0 < k < len(curve) - 1 and curve[0] > 0 and curve[k] / curve[0] < .99
    return {
        "hours_back": abs(ts[k]) / 3600.0,
        "origin_lon": float(L[k].mean()),
        "origin_lat": float(A[k].mean()),
        "criterion": criterion,
        "time_resolved": bool(time_resolved),
        "spread_m": float(curve[k]),
        "spread_at_observation_m": float(curve[0]),
        "contraction_ratio": float(curve[k] / curve[0]) if curve[0] > 0 else 1.0,
        "hours": (np.abs(ts) / 3600.0).tolist(),
        "minor_curve_m": minor.tolist(),
        "total_curve_m": total.tolist(),
        "track_lon": L[:, :].mean(1).tolist(),
        "track_lat": A[:, :].mean(1).tolist(),
    }


def seed_from_polygon(geojson_geom, n=500, seed=0):
    """Uniformly sample n points inside a GeoJSON Polygon (rejection sampling)."""
    from shapely.geometry import shape
    poly = shape(geojson_geom)
    if n < 3 or poly.is_empty or not poly.is_valid or poly.geom_type not in {"Polygon", "MultiPolygon"} or poly.area <= 0:
        raise ValueError("A valid nonempty polygon and at least three particles are required")
    minx, miny, maxx, maxy = poly.bounds
    rng = np.random.default_rng(seed)
    out = []
    attempts = 0
    while len(out) < n:
        attempts += 1
        if attempts > 10000:
            raise ValueError("Polygon sampling failed; geometry is too thin for rejection sampling")
        xs = rng.uniform(minx, maxx, n)
        ys = rng.uniform(miny, maxy, n)
        for x, y in zip(xs, ys):
            if len(out) >= n:
                break
            if poly.contains(__import__("shapely").geometry.Point(x, y)):
                out.append((x, y))
    a = np.array(out)
    return a[:, 0], a[:, 1]
