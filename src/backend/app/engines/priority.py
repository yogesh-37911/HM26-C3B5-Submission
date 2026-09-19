"""Priority Engine.

Answers "what should be fixed first?" - a different question from the neglect
engine, which answers "what is about to be forgotten?".

Deliberate design choice: report count is capped at 15 of 100 points. A brigaded
complaint cannot outrank a genuine hazard. Severity, public-safety impact and
sensitive-location proximity together carry 60 points.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

MODEL_VERSION = "priority-rule-v1"

WEIGHTS = {
    "severity": 25,
    "safety_impact": 20,
    "location_sensitivity": 15,
    "report_volume": 15,      # capped on purpose
    "age": 15,
    "vulnerable_exposure": 10,
}

#: Metres within which a sensitive place is considered "adjacent".
SENSITIVE_RADIUS_M = 250.0


@dataclass
class PFactor:
    code: str
    label: str
    points: float
    max_points: float
    detail: str

    def as_dict(self) -> dict:
        return {
            "code": self.code, "label": self.label,
            "points": round(self.points, 1), "max_points": self.max_points,
            "detail": self.detail,
        }


@dataclass
class PriorityResult:
    score: float
    level: str
    factors: list[PFactor] = field(default_factory=list)
    model_version: str = MODEL_VERSION

    def as_dict(self) -> dict:
        return {
            "priority_score": round(self.score),
            "priority_level": self.level,
            "priority_factors": [f.as_dict() for f in self.factors],
            "model_version": self.model_version,
            "weighting_note": (
                "Report volume is capped at 15/100 points by design so that a "
                "heavily-reported cosmetic issue cannot outrank a public-safety "
                "hazard."
            ),
        }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_priority(
    *,
    base_severity: int,
    safety_impact: int,
    nearby_sensitive: list[dict],
    duplicate_cluster_size: int,
    followup_count: int,
    created_at: datetime,
    sla_target_hours: float,
    is_recurring_location: bool = False,
    now: datetime | None = None,
) -> PriorityResult:
    """`nearby_sensitive` items look like {"type": "SCHOOL", "name": ..., "distance_m": 80}."""
    now = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    factors: list[PFactor] = []

    # 1. Intrinsic severity of the issue type.
    pts = (base_severity / 5.0) * WEIGHTS["severity"]
    factors.append(PFactor("severity", "Issue severity", pts, WEIGHTS["severity"],
                           f"Category carries a base severity of {base_severity}/5."))

    # 2. Direct public-safety hazard.
    pts = (safety_impact / 3.0) * WEIGHTS["safety_impact"]
    factors.append(PFactor(
        "safety_impact", "Public safety impact", pts, WEIGHTS["safety_impact"],
        f"Public-safety impact rated {safety_impact}/3 for this category.",
    ))

    # 3. Location sensitivity -- schools, hospitals, major junctions.
    weights_by_type = {"HOSPITAL": 1.0, "SCHOOL": 0.9, "JUNCTION": 0.7,
                       "MARKET": 0.6, "BUS_STAND": 0.6}
    best = 0.0
    named = []
    for place in nearby_sensitive:
        if place.get("distance_m", 9e9) > SENSITIVE_RADIUS_M:
            continue
        w = weights_by_type.get(place.get("type", ""), 0.5)
        # Closer matters more.
        proximity = 1.0 - (place["distance_m"] / SENSITIVE_RADIUS_M)
        best = max(best, w * (0.5 + 0.5 * proximity))
        named.append(f"{place.get('name', place.get('type'))} ({place['distance_m']:.0f}m)")
    pts = best * WEIGHTS["location_sensitivity"]
    factors.append(PFactor(
        "location_sensitivity", "Sensitive location proximity", pts,
        WEIGHTS["location_sensitivity"],
        "Near " + ", ".join(named[:3]) if named
        else "No school, hospital or major junction within 250m.",
    ))

    # 4. How many people are affected -- capped.
    volume = duplicate_cluster_size + followup_count * 0.5
    pts = _clamp(volume / 8.0, 0, 1.0) * WEIGHTS["report_volume"]
    factors.append(PFactor(
        "report_volume", "Number of affected reports", pts, WEIGHTS["report_volume"],
        f"{duplicate_cluster_size} report(s) in this cluster and "
        f"{followup_count} follow-up(s). Capped at {WEIGHTS['report_volume']} points.",
    ))

    # 5. Age relative to its own SLA.
    age_h = (now - created_at).total_seconds() / 3600.0
    ratio = age_h / max(sla_target_hours, 1.0)
    pts = _clamp(ratio, 0, 1.0) * WEIGHTS["age"]
    factors.append(PFactor(
        "age", "Time elapsed", pts, WEIGHTS["age"],
        f"Open for {age_h:.0f}h against a {sla_target_hours:.0f}h target.",
    ))

    # 6. Recurring failure at the same spot.
    pts = WEIGHTS["vulnerable_exposure"] if is_recurring_location else 0.0
    factors.append(PFactor(
        "vulnerable_exposure", "Recurring location", pts,
        WEIGHTS["vulnerable_exposure"],
        "This location has produced repeated complaints in the last 90 days."
        if is_recurring_location else "No repeat pattern at this location.",
    ))

    score = _clamp(sum(f.points for f in factors), 0, 100)
    level = ("CRITICAL" if score >= 75 else "HIGH" if score >= 55
             else "MEDIUM" if score >= 32 else "LOW")

    # Safety override: a severe, hazardous issue next to a hospital or school
    # is never allowed to fall below HIGH regardless of arithmetic.
    if safety_impact >= 3 and best >= 0.8 and level in {"MEDIUM", "LOW"}:
        level = "HIGH"
        factors.append(PFactor(
            "safety_override", "Safety override applied", 0, 0,
            "Escalated to HIGH: severe hazard adjacent to a school or hospital.",
        ))

    return PriorityResult(score=score, level=level,
                          factors=sorted(factors, key=lambda f: f.points, reverse=True))
