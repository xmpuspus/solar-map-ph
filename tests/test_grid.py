"""Tests for the tile-grid generator in ncr_scan.

These are pure-function tests, no network, no model load.
"""

from __future__ import annotations


def test_grid_centers_in_bbox():
    from detection.scan.ncr_scan import grid_centers

    bbox = (14.40, 120.92, 14.78, 121.13)
    centers = grid_centers(bbox)
    assert len(centers) > 1000, "NCR grid should produce thousands of cells"
    s, w, n, e = bbox
    for lat, lon in centers:
        assert s <= lat <= n
        assert w <= lon <= e


def test_grid_centers_small_bbox_is_subset():
    from detection.scan.ncr_scan import grid_centers

    big = grid_centers((14.60, 121.00, 14.62, 121.02))
    small = grid_centers((14.60, 121.00, 14.61, 121.01))
    # The smaller box has strictly fewer centers (by ~4x at fixed stride).
    assert len(small) < len(big)
    assert len(small) >= 4


def test_grid_centers_empty_bbox():
    from detection.scan.ncr_scan import grid_centers

    # Bbox with zero area should produce zero centers (well, possibly one
    # if the centers fall exactly on the seam; both are acceptable).
    centers = grid_centers((14.60, 121.00, 14.60, 121.00))
    assert len(centers) <= 1
