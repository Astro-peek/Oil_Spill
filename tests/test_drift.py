"""Self-check for drift.py. Every case has an answer computable by hand."""
import math
import numpy as np
from oilspill.drift import (UniformField, ShearField, DriftField, advect, spread_m,
                   minor_spread_m, hindcast_origin, m_per_deg_lon, R_LAT_M)


def test_uniform_advection_distance():
    """1 m/s east for 10 h must move exactly 36 km east and 0 north."""
    ts, L, A = advect([4.0], [55.0], UniformField(1.0, 0.0), hours=10, dt_s=900)
    dx = (L[-1, 0] - 4.0) * m_per_deg_lon(55.0)
    dy = (A[-1, 0] - 55.0) * R_LAT_M
    assert abs(dx - 36000) < 50, dx
    assert abs(dy) < 1e-6, dy


def test_northward_and_time_reversal():
    f = UniformField(0.3, 0.7)
    ts, L, A = advect([10.0], [40.0], f, hours=6)
    dy = (A[-1, 0] - 40.0) * R_LAT_M
    assert abs(dy - 0.7 * 6 * 3600) < 50, dy
    # advecting back from the endpoint must return to the start
    ts2, L2, A2 = advect([L[-1, 0]], [A[-1, 0]], f, hours=-6)
    assert abs(L2[-1, 0] - 10.0) < 1e-6 and abs(A2[-1, 0] - 40.0) < 1e-6


def test_windage_fraction():
    """No current, 10 m/s wind, 3% windage => slick moves at 0.3 m/s."""
    f = DriftField(current=None, wind=UniformField(10.0, 0.0), windage=0.03)
    ts, L, A = advect([0.0], [0.0], f, hours=1)
    dx = (L[-1, 0] - 0.0) * m_per_deg_lon(0.0)
    assert abs(dx - 0.3 * 3600) < 20, dx


def test_current_plus_wind_adds():
    f = DriftField(current=UniformField(0.2, 0.0), wind=UniformField(10.0, 0.0), windage=0.03)
    ts, L, A = advect([0.0], [0.0], f, hours=1)
    dx = (L[-1, 0] - 0.0) * m_per_deg_lon(0.0)
    assert abs(dx - 0.5 * 3600) < 20, dx      # 0.2 current + 0.3 windage


def test_diffusion_grows_cloud():
    lon = np.zeros(2000); lat = np.zeros(2000)
    _, L, A = advect(lon, lat, UniformField(0, 0), hours=6, diffusivity=10.0, seed=1)
    s0, s1 = spread_m(L[0], A[0]), spread_m(L[-1], A[-1])
    assert s0 == 0.0 and s1 > 100, (s0, s1)
    # random walk: spread ~ sqrt(2*2K*t) over 2 dims; just assert the right order of magnitude
    exp = math.sqrt(2 * 2 * 10.0 * 6 * 3600)
    assert 0.5 * exp < s1 < 2.0 * exp, (s1, exp)


def test_uniform_field_cannot_recover_origin_time():
    """Documented limitation: a rigid translation never contracts, so no origin time exists."""
    rng = np.random.default_rng(0)
    lon = 4.0 + rng.normal(0, 0.02, 400); lat = 55.0 + rng.normal(0, 0.02, 400)
    r = hindcast_origin(lon, lat, UniformField(0.5, 0.2), max_hours=24)
    assert r["contraction_ratio"] > 0.95, r["contraction_ratio"]
    assert r["time_resolved"] is False, "uniform field carries no timing information"


class DivergentField:
    """Radial divergence: u = k*dx, v = k*dy. A point release grows into a blob."""
    def __init__(self, k, lon0, lat0):
        self.k, self.lon0, self.lat0 = k, lon0, lat0

    def __call__(self, lon, lat, t):
        dx = (np.asarray(lon, float) - self.lon0) * m_per_deg_lon(self.lat0)
        dy = (np.asarray(lat, float) - self.lat0) * R_LAT_M
        return self.k * dx, self.k * dy


class CurvedShearField:
    """u grows with dy^2, so a straight N-S line bends into a parabola (width grows from zero)."""
    def __init__(self, k, lat0):
        self.k, self.lat0 = k, lat0

    def __call__(self, lon, lat, t):
        dy = (np.asarray(lat, float) - self.lat0) * R_LAT_M
        return self.k * dy * dy, np.zeros_like(np.asarray(lat, float))


def test_divergence_recovers_location_but_not_time():
    """Pure divergence contracts monotonically backwards, so the time hits the search boundary.
    Location is still exact. The API must ADMIT the time is unresolved."""
    f = DivergentField(3e-5, 4.0, 55.0)
    rng = np.random.default_rng(0)
    lon = 4.0 + rng.normal(0, 2e-4, 400)
    lat = 55.0 + rng.normal(0, 2e-4, 400)
    _, L, A = advect(lon, lat, f, hours=10)
    r = hindcast_origin(L[-1], A[-1], f, max_hours=24, criterion="total")
    assert r["contraction_ratio"] < 0.2, r["contraction_ratio"]
    assert abs(r["origin_lon"] - 4.0) < 0.01 and abs(r["origin_lat"] - 55.0) < 0.01, r
    assert r["time_resolved"] is False, "boundary minimum must be reported as unresolved"
    assert abs(r["hours_back"] - 24.0) < 1e-6, r["hours_back"]


def test_curved_shear_recovers_line_origin():
    """Vessel line source: across-track width collapses at the release time."""
    lat0 = 55.0
    f = CurvedShearField(4e-10, lat0)
    rng = np.random.default_rng(0)
    lon = np.full(500, 4.0) + rng.normal(0, 1e-6, 500)
    lat = lat0 + rng.uniform(-0.05, 0.05, 500)
    hours = 12
    _, L, A = advect(lon, lat, f, hours=hours)
    r = hindcast_origin(L[-1], A[-1], f, max_hours=24, criterion="minor")
    assert r["contraction_ratio"] < 0.25, r["contraction_ratio"]
    assert r["time_resolved"] is True, "interior minimum should be reported as resolved"
    assert abs(r["hours_back"] - hours) < 1.5, r["hours_back"]


def test_minor_spread_detects_line():
    lat0 = 55.0
    lat = lat0 + np.linspace(-0.05, 0.05, 300)
    lon = np.full(300, 4.0)
    assert minor_spread_m(lon, lat) < 1.0                  # a perfect line has ~zero width
    rng = np.random.default_rng(0)
    blob_lon = 4.0 + rng.normal(0, 0.02, 300)
    assert minor_spread_m(blob_lon, lat) > 500             # a blob does not


def test_deflection_rotates_wind():
    """45 deg deflection of a due-east wind must give equal east and south components."""
    f = DriftField(wind=UniformField(10.0, 0.0), windage=0.03, deflection_deg=45.0)
    u, v = f(np.array([0.0]), np.array([0.0]), 0)
    assert abs(u[0] - 0.3 * math.cos(math.radians(45))) < 1e-9, u
    assert abs(v[0] + 0.3 * math.sin(math.radians(45))) < 1e-9, v


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print(f"  ok {k}")
    print("all drift checks passed")
