"""Self-check for ais.py: the planted culprit must win, and each signal must do its job."""
import pandas as pd
from oilspill.ais import synth_traffic, filter_traffic, score_vessels, haversine_km, COLS

ORIGIN = (34.8723, 35.2256)      # lon, lat
WHEN = "2016-10-06T15:40"
HB = 31.0                        # hindcast hours back


def _score(**kw):
    df = synth_traffic(*ORIGIN, WHEN, culprit_offset_h=HB, culprit_course=55.0, **kw)
    return df, score_vessels(df, *ORIGIN, WHEN, HB, slick_orientation_deg=55.0)


def test_schema():
    df = synth_traffic(*ORIGIN, WHEN)
    assert list(df.columns) == COLS
    assert df.MMSI.nunique() == 41                       # 40 background + 1 culprit


def test_culprit_ranks_first():
    df, s = _score()
    assert s, "no candidates survived filtering"
    assert s[0]["MMSI"] == 999000001, [(r["MMSI"], r["score"]) for r in s[:3]]
    assert s[0]["score"] > 60, s[0]["score"]
    if len(s) > 1:
        assert s[0]["score"] - s[1]["score"] > 15, "culprit must win clearly, not by a nose"


def test_culprit_signals_are_right():
    df, s = _score()
    top = s[0]
    # interpolated across the dark gap the vessel passes essentially over the origin, while its
    # last ACTUAL fix is ~11 km out — that difference is itself the evidence
    assert top["cpa_km"] < 2.0, top["cpa_km"]
    assert top["cpa_km_observed"] > 5.0, top["cpa_km_observed"]
    assert top["dt_hours"] < 2.0, top["dt_hours"]        # at the hindcast time
    assert top["gap_covers_origin"] is True              # went dark over the discharge
    assert top["speed_drop_kn"] > 3.0, top["speed_drop_kn"]
    assert top["align_deg"] < 15.0, top["align_deg"]     # steaming along the slick axis


def test_filter_removes_irrelevant_traffic():
    df = synth_traffic(*ORIGIN, WHEN, n_vessels=40)
    kept, _ = filter_traffic(df, *ORIGIN, WHEN, HB, radius_km=60.0)
    assert kept.MMSI.nunique() < df.MMSI.nunique(), "filter kept everything"
    assert 999000001 in set(kept.MMSI), "filter dropped the actual culprit"


def test_tight_radius_still_keeps_culprit():
    df = synth_traffic(*ORIGIN, WHEN)
    kept, _ = filter_traffic(df, *ORIGIN, WHEN, HB, radius_km=10.0)
    assert 999000001 in set(kept.MMSI)


def test_wrong_origin_time_demotes_culprit():
    """Timing must actually matter: hindcasting to the wrong hour should cost the culprit."""
    df = synth_traffic(*ORIGIN, WHEN, culprit_offset_h=HB)
    good = score_vessels(df, *ORIGIN, WHEN, HB, slick_orientation_deg=55.0)
    bad = score_vessels(df, *ORIGIN, WHEN, HB - 12, slick_orientation_deg=55.0)
    g = next(r for r in good if r["MMSI"] == 999000001)["score"]
    b = next((r for r in bad if r["MMSI"] == 999000001), {"score": 0})["score"]
    assert g > b, (g, b)


def test_haversine_known_distance():
    d = haversine_km(0.0, 0.0, 0.0, 1.0)                 # 1 degree of latitude
    assert abs(d - 111.19) < 0.5, d


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print(f"  ok {k}")
    print("all AIS checks passed")
