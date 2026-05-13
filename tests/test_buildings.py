"""Tests for the OSM building geometry helpers in detection/buildings/.

Pure-function tests on the polygon helpers, no network calls.
"""

from __future__ import annotations

import math


def test_polygon_area_unit_square():
    from detection.buildings.fetch_buildings import _polygon_area_m2

    # A degree-fraction square at Manila latitude. Side length picked so the
    # expected area is around 100 m^2.
    # 1 degree latitude ~ 111_320 m, so 0.0001 deg ~ 11.13 m
    coords = [
        [121.00, 14.60],
        [121.0001, 14.60],
        [121.0001, 14.6001],
        [121.00, 14.6001],
        [121.00, 14.60],
    ]
    area = _polygon_area_m2(coords)
    # 11.13 m * 11.13 m ~= 123.9 m^2 (longitude shrinks at lat 14.6 by cos(14.6))
    expected = 11.13 * 11.13 * math.cos(math.radians(14.6))
    assert 0.85 * expected <= area <= 1.15 * expected


def test_polygon_area_degenerate():
    from detection.buildings.fetch_buildings import _polygon_area_m2

    # A "line" (3 collinear points) should produce zero area, not crash.
    assert _polygon_area_m2([[0, 0], [1, 0], [2, 0], [0, 0]]) == 0.0
    # An empty / sub-minimum ring returns zero.
    assert _polygon_area_m2([[0, 0]]) == 0.0


def test_centroid():
    from detection.buildings.fetch_buildings import _centroid

    lon, lat = _centroid([[0, 0], [10, 0], [10, 10], [0, 10]])
    assert lon == 5.0
    assert lat == 5.0
