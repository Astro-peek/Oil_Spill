"""Deliverable (a): characterise a detected slick — geometric properties in real-world units.

Takes a binary mask plus its georeferenced SAR image, vectorises the slick, and measures it.
Masks in this corpus often carry no CRS of their own (Zenodo Part III), so geometry always comes
from the paired IMAGE, never the mask.

Areas/lengths are computed in a local UTM projection rather than in degrees: a degree of longitude
is ~64 km at 55N vs ~111 km at the equator, so measuring in degrees would be wrong by ~2x between
the North Sea and Red Sea scenes in this dataset.
"""
import argparse, json, math, os, glob, warnings
import numpy as np
import rasterio
from rasterio.features import shapes

# masks legitimately carry no geotransform here; we always take geometry from the paired image
warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform
from pyproj import CRS, Transformer


def utm_epsg(lon, lat):
    """EPSG code of the UTM zone containing this point."""
    zone = min(60, max(1, int((lon + 180) // 6) + 1))
    return (32600 if lat >= 0 else 32700) + zone


def _bearing(p, q):
    """Compass bearing of segment p->q in UTM metres, folded to [0,180) since an axis has no head."""
    return math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) % 180.0


def _axes(poly_utm):
    """(major_m, minor_m, orientation_deg) from the minimum rotated rectangle."""
    pts = list(poly_utm.minimum_rotated_rectangle.exterior.coords)[:4]
    if len(pts) < 4:
        return 0.0, 0.0, 0.0
    # Only the two ADJACENT edges are the rectangle's distinct sides; p2-p3 is parallel to p0-p1,
    # so taking the top two of three consecutive edges would return the long side twice.
    e = [(math.dist(pts[0], pts[1]), pts[0], pts[1]),
         (math.dist(pts[1], pts[2]), pts[1], pts[2])]
    e.sort(key=lambda t: -t[0])
    return e[0][0], e[1][0], _bearing(e[0][1], e[0][2])


def measure(image_path, mask_path=None, min_area_km2=0.01, mask_array=None):
    """Vectorise the mask and measure every slick in it. Returns (scene_summary, [slick, ...])."""
    with rasterio.open(image_path) as src:
        transform, crs = src.transform, src.crs
        res_x, res_y = src.res
        image_shape = src.shape
    if not math.isfinite(min_area_km2) or min_area_km2 < 0:
        raise ValueError("Minimum area must be finite and nonnegative")
    if crs is None:
        raise ValueError(f"{image_path} has no CRS; cannot measure in real units")

    if mask_array is None:
        with rasterio.open(mask_path) as m:
            arr = m.read(1)
    else:
        arr = mask_array                       # predicted mask, already in memory
    if arr.shape != image_shape:
        raise ValueError(f"Mask shape {arr.shape} does not match image shape {image_shape}")
    binary = (arr > 0).astype(np.uint8)

    polys = [shape(g) for g, v in shapes(binary, mask=binary.astype(bool), transform=transform) if v == 1]
    if not polys:
        return {"image": os.path.basename(image_path), "n_slicks": 0, "total_area_km2": 0.0,
                "detected": False}, []

    # Polygons come out in the image's own CRS, which may be geographic OR projected (real
    # Sentinel-1 GRD is often UTM). Go via lon/lat so the zone lookup gets degrees, and so the
    # reported centroid/bbox/GeoJSON are WGS84 as consumers expect.
    to_wgs = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True).transform
    cx = float(np.mean([p.centroid.x for p in polys]))
    cy = float(np.mean([p.centroid.y for p in polys]))
    lon0, lat0 = to_wgs(cx, cy)
    fwd = Transformer.from_crs(crs, CRS.from_epsg(utm_epsg(lon0, lat0)), always_xy=True).transform

    out = []
    for p in polys:
        pu = shp_transform(fwd, p)
        area_km2 = pu.area / 1e6
        if area_km2 < min_area_km2:
            continue
        major, minor, orient = _axes(pu)
        hull = pu.convex_hull.area
        pw = shp_transform(to_wgs, p)          # WGS84 copy for reporting
        c = pw.centroid
        out.append({
            "centroid_lon": round(c.x, 6), "centroid_lat": round(c.y, 6),
            "area_km2": round(area_km2, 4),
            "perimeter_km": round(pu.length / 1000, 4),
            "major_axis_km": round(major / 1000, 4),
            "minor_axis_km": round(minor / 1000, 4),
            "orientation_deg": round(orient, 1),          # 0=N-S axis, 90=E-W axis
            "elongation": round(major / minor, 3) if minor > 0 else None,
            "solidity": round(pu.area / hull, 3) if hull > 0 else None,
            # perimeter / perimeter-of-equal-area-circle: 1.0 = disc, higher = ragged/filamentary.
            # Slicks run high, wind-shadow look-alikes tend rounder.
            "compactness": round(pu.length / (2 * math.sqrt(math.pi * pu.area)), 3) if pu.area > 0 else None,
            "bbox": [round(v, 6) for v in pw.bounds],
            "geometry": mapping(pw),
        })

    out.sort(key=lambda d: -d["area_km2"])
    summary = {
        "image": os.path.basename(image_path),
        "crs": str(crs),
        "pixel_m": ([round(abs(res_x) * 111320 * math.cos(math.radians(lat0)), 2),
                     round(abs(res_y) * 110540, 2)] if CRS.from_user_input(crs).is_geographic
                    else [round(abs(res_x), 2), round(abs(res_y), 2)]),
        "detected": bool(out),
        "n_slicks": len(out),
        "total_area_km2": round(sum(d["area_km2"] for d in out), 4),
        "largest_area_km2": round(out[0]["area_km2"], 4) if out else 0.0,
        # centroid of the whole slick complex — seeds the drift hindcast (b) and the AIS query (c)
        "centroid_lon": round(float(np.average([d["centroid_lon"] for d in out],
                                               weights=[d["area_km2"] for d in out])), 6) if out else None,
        "centroid_lat": round(float(np.average([d["centroid_lat"] for d in out],
                                               weights=[d["area_km2"] for d in out])), 6) if out else None,
    }
    return summary, out


def geojson(slicks, props_from_summary=None):
    feats = []
    for s in slicks:
        p = {k: v for k, v in s.items() if k != "geometry"}
        if props_from_summary:
            p.update(props_from_summary)
        feats.append({"type": "Feature", "geometry": s["geometry"], "properties": p})
    return {"type": "FeatureCollection", "features": feats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="glob for georeferenced image tifs")
    ap.add_argument("--masks", required=True, help="dir holding the matching masks")
    ap.add_argument("--mask-suffix", default="", help="e.g. _segmentation for Part III")
    ap.add_argument("--min-area-km2", type=float, default=0.01)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="runs/geometry")
    a = ap.parse_args()

    files = sorted(glob.glob(a.images))
    if a.limit:
        files = files[:a.limit]
    os.makedirs(a.out, exist_ok=True)

    rows, all_feats = [], []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        mp = os.path.join(a.masks, f"{stem}{a.mask_suffix}.tif")
        if not os.path.exists(mp):
            print(f"[skip] no mask for {stem}")
            continue
        summary, slicks = measure(f, mp, a.min_area_km2)
        rows.append(summary)
        all_feats += geojson(slicks, {"source_image": summary["image"]})["features"]

    with open(os.path.join(a.out, "scenes.json"), "w") as fh:
        json.dump(rows, fh, indent=1)
    with open(os.path.join(a.out, "slicks.geojson"), "w") as fh:
        json.dump({"type": "FeatureCollection", "features": all_feats}, fh)

    det = [r for r in rows if r["detected"]]
    print(f"scenes={len(rows)} with_slick={len(det)} slicks={sum(r['n_slicks'] for r in rows)}")
    if det:
        for k in ["total_area_km2", "largest_area_km2"]:
            v = [r[k] for r in det]
            print(f"  {k}: min={min(v):.3f} median={np.median(v):.3f} max={max(v):.3f} km2")
    print(f"-> {a.out}/scenes.json, {a.out}/slicks.geojson")


if __name__ == "__main__":
    main()
