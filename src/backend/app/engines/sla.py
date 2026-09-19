"""SLA tracking.

All targets are CONFIGURABLE DEMONSTRATION VALUES seeded into `sla_rules`.
They are not official Mysuru City Corporation service commitments.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sla_state(
    *,
    created_at: datetime,
    target_hours: float,
    resolved_at: datetime | None = None,
    risk_score: float = 0.0,
    now: datetime | None = None,
) -> dict:
    """Elapsed / remaining / breach probability for one complaint."""
    now = now or datetime.now(timezone.utc)
    created_at = _aware(created_at)
    due_at = created_at + timedelta(hours=target_hours)

    end = _aware(resolved_at) if resolved_at else now
    elapsed_h = (end - created_at).total_seconds() / 3600.0
    remaining_h = (due_at - now).total_seconds() / 3600.0

    if resolved_at:
        breached = elapsed_h > target_hours
        return {
            "target_hours": target_hours,
            "elapsed_hours": round(elapsed_h, 2),
            "remaining_hours": 0.0,
            "due_at": due_at.isoformat(),
            "breached": breached,
            "breach_probability": 100 if breached else 0,
            "breach_risk": "BREACHED" if breached else "MET",
            "predicted_breach_at": None,
            "is_demo_value": True,
        }

    if remaining_h <= 0:
        prob = 100
    else:
        # Two independent pressures: how much of the window is gone, and how
        # likely the complaint is to stall (neglect risk). Blended, not summed.
        consumed = min(elapsed_h / max(target_hours, 1e-6), 1.0)
        prob = int(round(100 * min(1.0, 0.55 * consumed ** 1.6 + 0.45 * (risk_score / 100.0))))

    level = ("BREACHED" if remaining_h <= 0 else "HIGH" if prob >= 65
             else "MODERATE" if prob >= 35 else "LOW")

    return {
        "target_hours": target_hours,
        "elapsed_hours": round(elapsed_h, 2),
        "remaining_hours": round(max(remaining_h, 0.0), 2),
        "due_at": due_at.isoformat(),
        "breached": remaining_h <= 0,
        "breach_probability": prob,
        "breach_risk": level,
        "predicted_breach_at": due_at.isoformat() if prob >= 50 else None,
        "is_demo_value": True,
        "note": "Demonstration SLA target, configurable per category; not MCC policy.",
    }


def humanize_hours(hours: float) -> str:
    if hours <= 0:
        return "overdue"
    d, rem = divmod(int(hours), 24)
    h = rem
    if d:
        return f"{d}d {h}h"
    m = int((hours - int(hours)) * 60)
    return f"{h}h {m}m"
