"""Predictive Neglect Engine.

Estimates the likelihood that an OPEN complaint will go stale before it is
resolved, and explains itself.

Why a deterministic weighted model and not an ML classifier
-----------------------------------------------------------
We deliberately chose an interpretable additive scoring model over a
black-box classifier. The MVP has no real historical municipal outcome data
to train or calibrate on, and a civic officer acting on a prioritisation must
be able to see *why* a complaint was surfaced and contest it. An additive
model gives per-factor attribution for free. The interface below
(`compute_risk` -> score/level/factors/action) is the same shape a logistic
regression would produce, so swapping in a trained model later is a drop-in
change once real outcome data exists. See docs/limitations.md.

This is NOT a scientifically validated model. It is an MVP heuristic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

MODEL_VERSION = "neglect-rule-v1"

# Maximum points each factor can contribute. They sum to 100.
WEIGHTS = {
    "inactivity": 26,
    "historical_delay": 20,
    "assignment_gap": 18,
    "age": 14,
    "repeat_pressure": 12,
    "severity": 10,
}


@dataclass
class Factor:
    code: str
    label: str
    points: float
    max_points: float
    detail: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "points": round(self.points, 1),
            "max_points": self.max_points,
            "detail": self.detail,
        }


@dataclass
class RiskResult:
    score: float
    level: str
    factors: list[Factor] = field(default_factory=list)
    recommended_action: str = ""
    model_version: str = MODEL_VERSION

    def as_dict(self) -> dict:
        return {
            "risk_score": round(self.score),
            "risk_level": self.level,
            "risk_factors": [f.as_dict() for f in self.factors],
            "recommended_action": self.recommended_action,
            "model_version": self.model_version,
            "disclaimer": (
                "Neglect risk is an interpretable heuristic trained on no "
                "historical municipal outcomes. It ranks attention, it does "
                "not predict fact."
            ),
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _hours_between(a: datetime, b: datetime) -> float:
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (b - a).total_seconds() / 3600.0


def compute_risk(
    *,
    created_at: datetime,
    last_action_at: datetime,
    status: str,
    sla_target_hours: float,
    category_avg_resolution_hours: float,
    jurisdiction_avg_resolution_hours: float | None,
    has_field_worker: bool,
    status_change_count: int,
    duplicate_count: int,
    followup_count: int,
    reopen_count: int,
    base_severity: int,
    safety_impact: int,
    has_evidence: bool,
    now: datetime | None = None,
) -> RiskResult:
    """Return a 0-100 neglect risk score with per-factor attribution."""
    now = now or datetime.now(timezone.utc)
    factors: list[Factor] = []

    # Resolved/rejected complaints cannot be neglected.
    if status in {"RESOLVED", "REJECTED"}:
        return RiskResult(
            score=0.0,
            level="LOW",
            factors=[Factor("closed", "Complaint is closed", 0, 0,
                            f"Status is {status}; neglect risk does not apply.")],
            recommended_action="No action required. Complaint is closed.",
        )

    age_h = _hours_between(created_at, now)
    idle_h = _hours_between(last_action_at, now)

    # 1. Inactivity -- the single strongest stagnation signal. Scaled against
    #    the SLA target so a 30h silence means more on a 24h SLA than a 72h one.
    idle_ratio = idle_h / max(sla_target_hours, 1.0)
    pts = _clamp(idle_ratio, 0, 1.0) * WEIGHTS["inactivity"]
    factors.append(Factor(
        "inactivity", "Time since last action", pts, WEIGHTS["inactivity"],
        f"No recorded action for {idle_h:.0f} hours "
        f"({idle_ratio * 100:.0f}% of the {sla_target_hours:.0f}h SLA window).",
    ))

    # 2. Historical delay -- does this category/ward habitually run late?
    hist = max(category_avg_resolution_hours, 1.0)
    if jurisdiction_avg_resolution_hours:
        hist = (hist + jurisdiction_avg_resolution_hours) / 2.0
    overrun = hist / max(sla_target_hours, 1.0)
    pts = _clamp((overrun - 0.5) / 1.5, 0, 1.0) * WEIGHTS["historical_delay"]
    factors.append(Factor(
        "historical_delay", "Historical delay for this category/ward", pts,
        WEIGHTS["historical_delay"],
        f"Similar complaints historically take {hist:.0f}h against a "
        f"{sla_target_hours:.0f}h target.",
    ))

    # 3. Assignment gap -- unowned work is the work that disappears.
    if has_field_worker:
        pts, detail = 0.0, "A field worker is assigned and accountable."
    elif status in {"SUBMITTED", "VALIDATING", "ROUTED"}:
        # Grows with how long it has sat unassigned.
        pts = _clamp(age_h / max(sla_target_hours * 0.5, 1.0), 0, 1.0) * WEIGHTS["assignment_gap"]
        detail = f"No field worker assigned {age_h:.0f}h after submission."
    else:
        pts = WEIGHTS["assignment_gap"] * 0.4
        detail = f"Status is {status} but no active field assignment exists."
    factors.append(Factor("assignment_gap", "Assignment status", pts,
                          WEIGHTS["assignment_gap"], detail))

    # 4. Raw age past SLA.
    age_ratio = age_h / max(sla_target_hours, 1.0)
    pts = _clamp(age_ratio / 2.0, 0, 1.0) * WEIGHTS["age"]
    factors.append(Factor(
        "age", "Complaint age", pts, WEIGHTS["age"],
        f"Open for {age_h:.0f}h ({age_ratio * 100:.0f}% of SLA target elapsed).",
    ))

    # 5. Repeat pressure -- duplicates, follow-ups and reopens all mean the
    #    public has not stopped caring, and a reopen means we already failed.
    signal = duplicate_count * 1.0 + followup_count * 0.8 + reopen_count * 2.5
    pts = _clamp(signal / 6.0, 0, 1.0) * WEIGHTS["repeat_pressure"]
    bits = []
    if duplicate_count:
        bits.append(f"{duplicate_count} related report(s) nearby")
    if followup_count:
        bits.append(f"{followup_count} citizen follow-up(s)")
    if reopen_count:
        bits.append(f"reopened {reopen_count} time(s)")
    factors.append(Factor(
        "repeat_pressure", "Citizen pressure and repeats", pts,
        WEIGHTS["repeat_pressure"],
        "; ".join(bits) if bits else "No duplicates, follow-ups or reopens recorded.",
    ))

    # 6. Severity -- a neglected hazard costs more than a neglected nuisance.
    sev_norm = (base_severity / 5.0) * 0.7 + (safety_impact / 3.0) * 0.3
    pts = _clamp(sev_norm, 0, 1.0) * WEIGHTS["severity"]
    factors.append(Factor(
        "severity", "Issue severity", pts, WEIGHTS["severity"],
        f"Category severity {base_severity}/5, public-safety impact {safety_impact}/3.",
    ))

    # Missing evidence slows verification, so it slightly raises stagnation risk.
    score = sum(f.points for f in factors)
    if not has_evidence:
        score += 3
        factors.append(Factor(
            "no_evidence", "No photo evidence", 3, 3,
            "No photo attached, so the issue needs a site visit before it can "
            "be confirmed.",
        ))
    # Churn without progress: many status flips but still open.
    if status_change_count >= 4 and status not in {"FIELD_VERIFIED"}:
        score += 4
        factors.append(Factor(
            "churn", "Status churn", 4, 4,
            f"{status_change_count} status changes without reaching resolution.",
        ))

    score = _clamp(score, 0, 100)
    level = "HIGH" if score >= 70 else "MODERATE" if score >= 40 else "LOW"

    return RiskResult(
        score=score,
        level=level,
        factors=sorted(factors, key=lambda f: f.points, reverse=True),
        recommended_action=_recommend(level, has_field_worker, idle_h, sla_target_hours,
                                      duplicate_count),
    )


def _recommend(level: str, has_worker: bool, idle_h: float, sla_h: float,
               dup_count: int) -> str:
    if level == "LOW":
        return "On track. Review at next scheduled queue sweep."
    if not has_worker:
        window = 6 if level == "HIGH" else 24
        base = f"Assign a field worker and review within {window} hours."
    else:
        base = (f"Contact the assigned field worker for a status update "
                f"({idle_h:.0f}h since last action).")
    if dup_count >= 3:
        base += f" {dup_count} nearby reports suggest a cluster - consider a single area-wide job."
    return base
