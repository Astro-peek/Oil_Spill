"""Self-check for spill_geometry: the failure here is silent, wrong NUMBERS, not a crash."""
import math, tempfile
import numpy as np, rasterio
from rasterio.transform import from_origin
from oilspill.spill_geometry import measure, utm_epsg

TMP = tempfile.mkdtemp()


def _write(path, arr, crs, transform, dtype="uint8"):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype=dtype, crs=crs, transform=transform) as d:
        d.write(arr.astype(dtype), 1)


def _scene(name, mask, crs, transform, mask_crs="same"):
    ip, mp = f"{TMP}/{name}_img.tif", f"{TMP}/{name}_msk.tif"
    _write(ip, np.zeros_like(mask, dtype="float32"), crs, transform, "float32")
    _write(mp, mask, crs if mask_crs == "same" else None, transform)
    return ip, mp


def test_utm_exact():
    """10 m pixels in UTM: a 100x200 px block must measure exactly 1 km x 2 km = 2 km2."""
    m = np.zeros((400, 400), np.uint8)
    m[100:300, 150:250] = 1
    tr = from_origin(500000, 6100000, 10, 10)
    s, sl = measure(*_scene("utm", m, "EPSG:32631", tr))
    assert s["n_slicks"] == 1, s
    d = sl[0]
    assert abs(d["area_km2"] - 2.0) < 1e-6, d["area_km2"]
    assert abs(d["perimeter_km"] - 6.0) < 1e-6, d["perimeter_km"]
    assert abs(d["major_axis_km"] - 2.0) < 1e-6, d["major_axis_km"]
    assert abs(d["minor_axis_km"] - 1.0) < 1e-6, d["minor_axis_km"]
    assert abs(d["elongation"] - 2.0) < 1e-3, d["elongation"]
    assert abs(d["orientation_deg"] - 0.0) < 1e-6, d["orientation_deg"]
    assert abs(d["solidity"] - 1.0) < 1e-6, d["solidity"]


def test_orientation_ew():
    m = np.zeros((400, 400), np.uint8)
    m[150:250, 100:300] = 1
    tr = from_origin(500000, 6100000, 10, 10)
    _, sl = measure(*_scene("ew", m, "EPSG:32631", tr))
    assert abs(sl[0]["orientation_deg"] - 90.0) < 1e-6, sl[0]["orientation_deg"]


def test_degrees_are_not_used():
    """The real trap: measuring in EPSG:4326 degrees instead of metres."""
    m = np.zeros((200, 200), np.uint8)
    m[50:150, 50:150] = 1
    tr = from_origin(4.0, 55.0, 1e-4, 1e-4)
    s, sl = measure(*_scene("deg", m, "EPSG:4326", tr))
    exp = (0.01 * 110540) * (0.01 * 111320 * math.cos(math.radians(55))) / 1e6
    got = sl[0]["area_km2"]
    assert abs(got - exp) / exp < 0.02, f"got {got} expected ~{exp}"
    assert got > 0.01, "area looks like square degrees, not km2"
    assert abs(sl[0]["elongation"] - 1.74) < 0.1, sl[0]["elongation"]


def test_mask_without_crs():
    """Part III masks carry no CRS; geometry must come from the paired image anyway."""
    m = np.zeros((400, 400), np.uint8); m[100:300, 150:250] = 1
    tr = from_origin(500000, 6100000, 10, 10)
    s, sl = measure(*_scene("nocrs", m, "EPSG:32631", tr, mask_crs=None))
    assert abs(sl[0]["area_km2"] - 2.0) < 1e-6, sl[0]["area_km2"]


def test_empty_and_filter():
    tr = from_origin(500000, 6100000, 10, 10)
    s, sl = measure(*_scene("empty", np.zeros((100, 100), np.uint8), "EPSG:32631", tr))
    assert s["detected"] is False and s["n_slicks"] == 0 and sl == []
    m = np.zeros((100, 100), np.uint8); m[10:13, 10:13] = 1
    s2, _ = measure(*_scene("tiny", m, "EPSG:32631", tr), min_area_km2=0.01)
    assert s2["n_slicks"] == 0, "speck should be filtered"


def test_multi_slick_and_centroid():
    m = np.zeros((400, 400), np.uint8)
    m[50:150, 50:150] = 1
    m[250:350, 250:350] = 1
    tr = from_origin(500000, 6100000, 10, 10)
    s, sl = measure(*_scene("multi", m, "EPSG:32631", tr))
    assert s["n_slicks"] == 2 and abs(s["total_area_km2"] - 2.0) < 1e-6, s
    assert sl[0]["area_km2"] >= sl[1]["area_km2"], "slicks must be sorted largest-first"


def test_utm_zone():
    assert utm_epsg(4.0, 55.0) == 32631
    assert utm_epsg(35.0, 35.0) == 32636
    assert utm_epsg(4.0, -55.0) == 32731


if __name__ == "__main__":
    for f in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        f(); print(f"  ok {f.__name__}")
    print("all geometry checks passed")
