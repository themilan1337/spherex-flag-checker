"""Query text and proper-motion helper (no network)."""

import pytest

from spherex_flags.extract import Target, position_at
from spherex_flags.irsa import coverage_query


def test_coverage_query_uses_the_documented_tables_and_a_point_in_polygon_test():
    q = coverage_query(300.18213726, 22.71085365)
    assert "FROM spherex.artifact a JOIN spherex.plane p ON a.planeid = p.planeid" in q
    assert "1 = CONTAINS(POINT('ICRS', 300.18213726, 22.71085365), p.poly)" in q
    assert q.endswith("ORDER BY p.time_bounds_lower")


def test_proper_motion_moves_the_position_linearly_from_j2000():
    t = Target("x", 100.0, 0.0, pmra_masyr=1000.0, pmdec_masyr=-500.0)
    ra, dec = position_at(t, 51544.5)
    assert (ra, dec) == (100.0, 0.0)
    ra, dec = position_at(t, 51544.5 + 10 * 365.25)  # ten years later
    assert ra == pytest.approx(100.0 + 10 * 1.0 / 3600.0)  # 1 arcsec/yr at dec 0
    assert dec == pytest.approx(-10 * 0.5 / 3600.0)


def test_right_ascension_shift_is_divided_by_cos_dec():
    t = Target("x", 10.0, 60.0, pmra_masyr=1000.0)
    ra, _ = position_at(t, 51544.5 + 365.25)
    assert ra - 10.0 == pytest.approx(1.0 / 3600.0 / 0.5, rel=1e-6)


def test_gaia_positions_are_moved_back_to_j2000():
    from spherex_flags.irsa import gaia_to_j2000

    ra0, dec0 = gaia_to_j2000(10.0, 0.0, pmra_masyr=1000.0, pmdec_masyr=2000.0, epoch=2016.0)
    assert ra0 == pytest.approx(10.0 - 16.0 / 3600.0)
    assert dec0 == pytest.approx(-32.0 / 3600.0)
    assert gaia_to_j2000(10.0, 20.0, 5.0, 5.0, epoch=2000.0) == (10.0, 20.0)
