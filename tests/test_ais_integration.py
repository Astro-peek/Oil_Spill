"""Regression checks for AIS ingestion, interpolation and gap scoring."""
import tempfile
from pathlib import Path
import pandas as pd
from oilspill.ais import load_ais, interp_track, score_vessels


def fixes(times, lon=None, cog=None):
    n = len(times)
    return pd.DataFrame(dict(MMSI=[123456789]*n, BaseDateTime=pd.to_datetime(times),
                             LAT=[0.0]*n, LON=lon or [0.0]*n, SOG=[10.0]*n,
                             COG=cog or [0.0]*n, VesselName=['Test']*n))


def test_csv_validation_and_utc():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/'ais.csv'
        df = fixes(['2026-01-01 05:30'])
        df['BaseDateTime'] = '2026-01-01T05:30:00+05:30'
        pd.concat([df, df]).to_csv(path, index=False)
        loaded = load_ais(path)
        assert len(loaded) == 1
        assert loaded.BaseDateTime.iloc[0] == pd.Timestamp('2026-01-01')
        df['LAT'] = 91
        df.to_csv(path, index=False)
        try:
            load_ais(path)
        except ValueError as exc:
            assert 'invalid fixes' in str(exc)
        else:
            raise AssertionError('invalid latitude accepted')


def test_course_wrap_and_exact_fix_times():
    df = fixes(['2026-01-01 00:02', '2026-01-01 00:12'], cog=[359, 1])
    gi = interp_track(df, pd.Timestamp('2026-01-01'), pd.Timestamp('2026-01-01 01:00'))
    assert gi.index.min() == df.BaseDateTime.min()
    assert gi.index.max() == df.BaseDateTime.max()
    assert abs(gi.loc['2026-01-01 00:07', 'COG']) < 1e-8


def test_origin_gap_is_not_hidden_by_larger_unrelated_gap():
    df = fixes(['2025-12-30 00:00', '2025-12-31 00:00', '2025-12-31 23:00',
                '2026-01-01 01:00', '2026-01-01 02:00'])
    row = score_vessels(df, 0, 0, '2026-01-01T06:00Z', 6, 0, pad_h=2)[0]
    assert row['gap_covers_origin']
    assert row['origin_gap_min'] == 120
    assert row['cpa_time'].endswith('Z')


def test_unrelated_gaps_do_not_add_score():
    df = fixes(['2025-12-30 00:00', '2025-12-31 00:00', '2025-12-31 23:00',
                '2026-01-01 00:00', '2026-01-01 01:00'])
    # A narrow window fully within the final one-hour segment.
    row = score_vessels(df, 0, 0, '2026-01-01 00:30', 0, 0, pad_h=.1)[0]
    assert row['max_gap_min'] == 60


if __name__ == '__main__':
    for name, test in sorted(list(globals().items())):
        if name.startswith('test_'):
            test()
            print('ok', name)
