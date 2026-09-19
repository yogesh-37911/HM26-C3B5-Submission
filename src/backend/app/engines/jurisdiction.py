"""Jurisdiction routing against *versioned* boundaries.

HackMysuru explicitly flags that Mysuru's boundaries are changing. So nothing
in this system says "Kuvempunagar belongs to MCC". Instead:

    Jurisdiction (stable identity: authority + ward)
      └── JurisdictionVersion (boundary geometry, effective_from..effective_to)

Routing always asks: *which boundary version was active at time T, and does the
point fall inside it?* A complaint stores the version id it was routed under,
so re-drawing a ward next month never rewrites last month's records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .geo import distance_to_polygon_centroid, haversine_m, point_in_polygon

MODEL_VERSION = "routing-v1"


@dataclass
class RouteResult:
    jurisdiction_id: int | None
    jurisdiction_version_id: int | None
    authority: str
    authority_type: str
    ward_number: int | None
    version_label: str | None
    confidence: float
    reason: str
    method: str  # CONTAINMENT / NEAREST / UNRESOLVED
    alternatives: list[dict]

    def as_dict(self) -> dict:
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "jurisdiction_version_id": self.jurisdiction_version_id,
            "authority": self.authority,
            "authority_type": self.authority_type,
            "ward": self.ward_number,
            "boundary_version": self.version_label,
            "confidence_pct": round(self.confidence * 100),
            "reason": self.reason,
            "method": self.method,
            "alternatives": self.alternatives,
            "model_version": MODEL_VERSION,
        }


def active_versions(all_versions: list, at: datetime) -> list:
    """Filter version rows whose validity window covers `at`."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    out = []
    for v in all_versions:
        start = v.effective_from
        end = v.effective_to
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if start <= at and (end is None or at < end):
            out.append(v)
    return out


def resolve(
    *,
    latitude: float,
    longitude: float,
    versions: list,
    jurisdiction_index: dict,
    at: datetime | None = None,
    nearest_fallback_m: float = 1200.0,
) -> RouteResult:
    """Resolve a coordinate to the authority whose boundary was active at `at`.

    `versions` are JurisdictionVersion rows (already bbox-prefiltered in SQL);
    `jurisdiction_index` maps jurisdiction_id -> Jurisdiction row.
    """
    at = at or datetime.now(timezone.utc)
    candidates = active_versions(versions, at)

    containing = []
    for v in candidates:
        if not (v.min_lat <= latitude <= v.max_lat and v.min_lng <= longitude <= v.max_lng):
            continue
        ring = v.boundary_json
        if point_in_polygon(latitude, longitude, ring):
            # Distance from the centroid tells us how confidently interior the
            # point is: dead-centre is unambiguous, a point hugging the edge is
            # a genuine coin-flip between two wards.
            d_centroid = distance_to_polygon_centroid(latitude, longitude, ring)
            containing.append((v, d_centroid))

    if containing:
        containing.sort(key=lambda t: t[1])
        v, d = containing[0]
        j = jurisdiction_index[v.jurisdiction_id]

        if len(containing) > 1:
            # Overlapping active boundaries: real, and worth surfacing honestly.
            confidence = 0.68
            reason = (f"Coordinates fall inside {len(containing)} overlapping active "
                      f"boundaries. Assigned to the nearest boundary centre "
                      f"({j.name}); officer review recommended.")
        else:
            edge_margin = _edge_margin(latitude, longitude, v.boundary_json)
            # >150m clear of any edge -> high confidence; on the line -> ~0.75.
            confidence = 0.75 + 0.23 * min(edge_margin / 150.0, 1.0)
            reason = (f"Coordinates fall inside the active {j.name} boundary "
                      f"(version {v.version_label}), {edge_margin:.0f}m from the "
                      f"nearest boundary edge.")

        alts = [{
            "authority": jurisdiction_index[cv.jurisdiction_id].authority,
            "ward": jurisdiction_index[cv.jurisdiction_id].ward_number,
            "version": cv.version_label,
            "centroid_distance_m": round(cd),
        } for cv, cd in containing[1:4]]

        return RouteResult(
            jurisdiction_id=j.id, jurisdiction_version_id=v.id,
            authority=j.authority, authority_type=j.authority_type,
            ward_number=j.ward_number, version_label=v.version_label,
            confidence=round(min(confidence, 0.98), 4), reason=reason,
            method="CONTAINMENT", alternatives=alts,
        )

    # No containment: fall back to nearest active boundary centroid, but say so.
    best = None
    for v in candidates:
        d = distance_to_polygon_centroid(latitude, longitude, v.boundary_json)
        if best is None or d < best[1]:
            best = (v, d)

    if best and best[1] <= nearest_fallback_m:
        v, d = best
        j = jurisdiction_index[v.jurisdiction_id]
        confidence = round(max(0.30, 0.62 - (d / nearest_fallback_m) * 0.30), 4)
        return RouteResult(
            jurisdiction_id=j.id, jurisdiction_version_id=v.id,
            authority=j.authority, authority_type=j.authority_type,
            ward_number=j.ward_number, version_label=v.version_label,
            confidence=confidence,
            reason=(f"Coordinates fall outside every active boundary. Routed to the "
                    f"nearest active jurisdiction ({j.name}, {d:.0f}m away). "
                    f"Manual confirmation recommended."),
            method="NEAREST", alternatives=[],
        )

    return RouteResult(
        jurisdiction_id=None, jurisdiction_version_id=None,
        authority="UNRESOLVED", authority_type="UNKNOWN", ward_number=None,
        version_label=None, confidence=0.0,
        reason=("Coordinates could not be matched to any jurisdiction boundary "
                "active at the time of reporting. Queued for manual routing."),
        method="UNRESOLVED", alternatives=[],
    )


def _edge_margin(lat: float, lng: float, ring: list[list[float]]) -> float:
    """Approximate metres from the point to the nearest boundary vertex."""
    return min(haversine_m(lat, lng, p[0], p[1]) for p in ring)
