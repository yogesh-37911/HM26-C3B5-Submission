"""Geospatial primitives without a PostGIS dependency.

Strategy: cheap bounding-box prefilter (index-friendly, runs in SQL) followed
by exact Haversine / ray-casting refinement in Python on the small candidate
set. Accurate enough at city scale; see docs/limitations.md for the trade-off.
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_for_radius(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lng, max_lng) covering a radius around a point.

    Used as an indexed SQL prefilter before exact distance is computed.
    """
    dlat = radius_m / 111_320.0
    # Guard against cos() -> 0 near the poles; irrelevant for Mysuru but cheap.
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    dlng = radius_m / (111_320.0 * cos_lat)
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def point_in_polygon(lat: float, lng: float, ring: list[list[float]]) -> bool:
    """Ray-casting test. `ring` is a closed/open list of [lat, lng] pairs."""
    if not ring or len(ring) < 3:
        return False
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        yi, xi = ring[i][0], ring[i][1]
        yj, xj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lng < x_cross:
                inside = not inside
        j = i
    return inside


def polygon_bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    lats = [p[0] for p in ring]
    lngs = [p[1] for p in ring]
    return min(lats), max(lats), min(lngs), max(lngs)


def centroid(ring: list[list[float]]) -> tuple[float, float]:
    lats = [p[0] for p in ring]
    lngs = [p[1] for p in ring]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def distance_to_polygon_centroid(lat: float, lng: float, ring: list[list[float]]) -> float:
    clat, clng = centroid(ring)
    return haversine_m(lat, lng, clat, clng)


def jitter_for_public(lat: float, lng: float, seed: int, radius_m: float = 120.0
                      ) -> tuple[float, float]:
    """Deterministically fuzz a coordinate for the public map.

    Exact citizen report locations are never exposed publicly. The offset is
    derived from the complaint id so the marker does not jump between page
    loads, but the true point cannot be recovered from the public API.
    """
    angle = (seed * 137.508) % 360.0
    dist = radius_m * (0.35 + ((seed * 31) % 65) / 100.0)
    dlat = (dist * math.cos(math.radians(angle))) / 111_320.0
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    dlng = (dist * math.sin(math.radians(angle))) / (111_320.0 * cos_lat)
    return round(lat + dlat, 6), round(lng + dlng, 6)
