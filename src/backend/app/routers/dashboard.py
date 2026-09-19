"""Public transparency dashboard.

Every endpoint here is unauthenticated and therefore must never leak citizen
identity or exact reported coordinates. Aggregates are computed in SQL; the
browser never receives the full complaint table.
"""
from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..engines.geo import jitter_for_public
from ..models import Assignment, Category, Complaint, Jurisdiction, utcnow

router = APIRouter(prefix="/api/dashboard", tags=["public-dashboard"])

OPEN_STATUSES = ["SUBMITTED", "VALIDATING", "ROUTED", "ASSIGNED",
                 "IN_PROGRESS", "FIELD_VERIFIED", "REOPENED"]

DISCLAIMER = ("Demo dataset - synthetic data generated for Mysuru CivicPulse "
              "demonstration. These figures do not represent real Mysuru "
              "civic records.")


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _resolution_hours_expr():
    """Average resolution time in hours, portable across SQLite and Postgres."""
    return None  # computed in Python below; see _avg_resolution.


def _avg_resolution(db: Session, *, jurisdiction_id: int | None = None,
                    category_id: int | None = None, limit: int = 2000) -> float | None:
    stmt = select(Complaint.created_at, Complaint.resolved_at).where(
        Complaint.resolved_at.is_not(None))
    if jurisdiction_id:
        stmt = stmt.where(Complaint.jurisdiction_id == jurisdiction_id)
    if category_id:
        stmt = stmt.where(Complaint.category_id == category_id)
    rows = db.execute(stmt.limit(limit)).all()
    if not rows:
        return None
    total = sum((_aware(r) - _aware(c)).total_seconds() / 3600.0 for c, r in rows)
    return round(total / len(rows), 1)


@router.get("/overview")
def overview(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=365)):
    since = utcnow() - timedelta(days=days)
    total = db.scalar(select(func.count(Complaint.id))) or 0
    open_n = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.status.in_(OPEN_STATUSES))) or 0
    resolved_n = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.status == "RESOLVED")) or 0
    high_risk = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.risk_level == "HIGH", Complaint.status.in_(OPEN_STATUSES))) or 0
    breached = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.sla_due_at < utcnow(), Complaint.status.in_(OPEN_STATUSES))) or 0
    stagnant = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.status.in_(OPEN_STATUSES),
        Complaint.last_action_at < utcnow() - timedelta(hours=72))) or 0
    recent = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.created_at >= since)) or 0

    by_cat = db.execute(
        select(Category.code, Category.name_en, Category.name_kn,
               func.count(Complaint.id))
        .join(Complaint, Complaint.category_id == Category.id)
        .group_by(Category.code, Category.name_en, Category.name_kn)
        .order_by(func.count(Complaint.id).desc())
    ).all()

    by_status = db.execute(
        select(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status)
    ).all()

    return {
        "total_complaints": total,
        "open_complaints": open_n,
        "resolved_complaints": resolved_n,
        "resolution_rate_pct": round(100 * resolved_n / total, 1) if total else 0.0,
        "avg_resolution_hours": _avg_resolution(db),
        "high_risk_open": high_risk,
        "sla_breached_open": breached,
        "stagnant_complaints": stagnant,
        "complaints_last_n_days": recent,
        "window_days": days,
        "by_category": [{"code": c, "name_en": en, "name_kn": kn, "count": n}
                        for c, en, kn, n in by_cat],
        "by_status": [{"status": s, "count": n} for s, n in by_status],
        "disclaimer": DISCLAIMER,
    }


@router.get("/wards")
def wards(db: Session = Depends(get_db), limit: int = Query(70, ge=1, le=200)):
    rows = db.execute(
        select(
            Jurisdiction.id, Jurisdiction.authority, Jurisdiction.ward_number,
            Jurisdiction.name,
            func.count(Complaint.id),
            func.sum(case((Complaint.status.in_(OPEN_STATUSES), 1), else_=0)),
            func.sum(case((Complaint.status == "RESOLVED", 1), else_=0)),
            func.sum(case((Complaint.risk_level == "HIGH", 1), else_=0)),
        )
        .join(Complaint, Complaint.jurisdiction_id == Jurisdiction.id, isouter=True)
        .group_by(Jurisdiction.id, Jurisdiction.authority,
                  Jurisdiction.ward_number, Jurisdiction.name)
        .order_by(func.count(Complaint.id).desc())
        .limit(limit)
    ).all()

    city_median = _avg_resolution(db) or 0.0
    items = []
    for jid, authority, ward, name, total, open_n, resolved_n, high_risk in rows:
        items.append({
            "jurisdiction_id": jid, "authority": authority, "ward": ward, "name": name,
            "total": total or 0, "open": int(open_n or 0),
            "resolved": int(resolved_n or 0), "high_risk": int(high_risk or 0),
            "avg_resolution_hours": _avg_resolution(db, jurisdiction_id=jid),
            "resolution_rate_pct": (round(100 * (resolved_n or 0) / total, 1)
                                    if total else 0.0),
        })
    return {"city_avg_resolution_hours": city_median, "items": items,
            "disclaimer": DISCLAIMER}


@router.get("/wards/{jurisdiction_id}/explain")
def explain_ward(jurisdiction_id: int, db: Session = Depends(get_db)):
    """"Why is this area behind?" - narrative reasons, not just a chart."""
    j = db.get(Jurisdiction, jurisdiction_id)
    if not j:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Jurisdiction not found")

    now = utcnow()
    open_n = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.jurisdiction_id == jurisdiction_id,
        Complaint.status.in_(OPEN_STATUSES))) or 0

    assigned_ids = select(Assignment.complaint_id).where(Assignment.is_active.is_(True))
    unassigned = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.jurisdiction_id == jurisdiction_id,
        Complaint.status.in_(OPEN_STATUSES),
        Complaint.id.not_in(assigned_ids))) or 0

    high_risk = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.jurisdiction_id == jurisdiction_id,
        Complaint.status.in_(OPEN_STATUSES), Complaint.risk_level == "HIGH")) or 0

    breached = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.jurisdiction_id == jurisdiction_id,
        Complaint.status.in_(OPEN_STATUSES), Complaint.sla_due_at < now)) or 0

    ward_avg = _avg_resolution(db, jurisdiction_id=jurisdiction_id)
    city_avg = _avg_resolution(db)

    # Week-on-week movement by category.
    this_week = now - timedelta(days=7)
    last_week = now - timedelta(days=14)
    cur = dict(db.execute(
        select(Category.name_en, func.count(Complaint.id))
        .join(Complaint, Complaint.category_id == Category.id)
        .where(Complaint.jurisdiction_id == jurisdiction_id,
               Complaint.created_at >= this_week)
        .group_by(Category.name_en)).all())
    prev = dict(db.execute(
        select(Category.name_en, func.count(Complaint.id))
        .join(Complaint, Complaint.category_id == Category.id)
        .where(Complaint.jurisdiction_id == jurisdiction_id,
               Complaint.created_at >= last_week,
               Complaint.created_at < this_week)
        .group_by(Category.name_en)).all())

    reasons: list[dict] = []
    if unassigned:
        reasons.append({
            "code": "UNASSIGNED_BACKLOG",
            "text": f"{unassigned} of {open_n} open complaints are still awaiting "
                    f"field assignment.",
            "metric": unassigned,
            "action": "Assign field workers to the unassigned queue.",
        })
    for name, count in sorted(cur.items(), key=lambda kv: -kv[1])[:3]:
        before = prev.get(name, 0)
        if before and count > before * 1.25:
            pct = round(100 * (count - before) / before)
            reasons.append({
                "code": "CATEGORY_SURGE",
                "text": f"{name} complaints increased {pct}% this week "
                        f"({before} to {count}).",
                "metric": pct,
                "action": f"Consider a scheduled {name.lower()} drive in this ward.",
            })
    if ward_avg and city_avg and ward_avg > city_avg:
        delta = round(ward_avg - city_avg, 1)
        reasons.append({
            "code": "SLOWER_THAN_CITY",
            "text": f"Average resolution time is {delta}h above the city average "
                    f"({ward_avg}h vs {city_avg}h).",
            "metric": delta,
            "action": "Review recurring bottlenecks in this ward's workflow.",
        })
    if high_risk:
        reasons.append({
            "code": "HIGH_NEGLECT_RISK",
            "text": f"{high_risk} complaints are at high neglect risk and are "
                    f"likely to go stale without intervention.",
            "metric": high_risk,
            "action": "Work the high-risk queue before the next SLA window closes.",
        })
    if breached:
        reasons.append({
            "code": "SLA_BREACH",
            "text": f"{breached} open complaints have already passed their "
                    f"demonstration SLA target.",
            "metric": breached,
            "action": "Escalate breached complaints to the ward officer.",
        })
    if not reasons:
        reasons.append({
            "code": "ON_TRACK",
            "text": "No systemic backlog detected. Open complaints are assigned "
                    "and within their SLA windows.",
            "metric": 0, "action": "Maintain current cadence.",
        })

    return {
        "jurisdiction": {"id": j.id, "authority": j.authority,
                         "ward": j.ward_number, "name": j.name},
        "open_complaints": open_n,
        "unassigned": unassigned,
        "high_risk": high_risk,
        "sla_breached": breached,
        "ward_avg_resolution_hours": ward_avg,
        "city_avg_resolution_hours": city_avg,
        "reasons": reasons,
        "disclaimer": DISCLAIMER,
    }


@router.get("/trends")
def trends(db: Session = Depends(get_db), days: int = Query(30, ge=7, le=180),
           ward: int | None = None):
    since = utcnow() - timedelta(days=days)
    stmt = select(Complaint.created_at, Complaint.resolved_at).where(
        Complaint.created_at >= since)
    if ward is not None:
        jids = select(Jurisdiction.id).where(Jurisdiction.ward_number == ward)
        stmt = stmt.where(Complaint.jurisdiction_id.in_(jids))

    buckets: dict[str, dict] = {}
    for created, resolved in db.execute(stmt).all():
        key = _aware(created).date().isoformat()
        buckets.setdefault(key, {"date": key, "submitted": 0, "resolved": 0})
        buckets[key]["submitted"] += 1
        if resolved:
            rkey = _aware(resolved).date().isoformat()
            buckets.setdefault(rkey, {"date": rkey, "submitted": 0, "resolved": 0})
            buckets[rkey]["resolved"] += 1
    series = sorted(buckets.values(), key=lambda b: b["date"])
    return {"days": days, "ward": ward, "series": series, "disclaimer": DISCLAIMER}


@router.get("/map")
def map_markers(
    db: Session = Depends(get_db),
    min_lat: float = Query(...), max_lat: float = Query(...),
    min_lng: float = Query(...), max_lng: float = Query(...),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
):
    """Bounding-box query. The browser never loads the full complaint table."""
    stmt = select(Complaint).where(
        Complaint.latitude.between(min_lat, max_lat),
        Complaint.longitude.between(min_lng, max_lng),
    )
    if status_filter:
        stmt = stmt.where(Complaint.status.in_(status_filter.split(",")))
    if category:
        cat = db.scalar(select(Category).where(Category.code == category))
        stmt = stmt.where(Complaint.category_id == (cat.id if cat else -1))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(Complaint.risk_score.desc()).limit(limit)))

    markers = []
    for c in rows:
        lat, lng = jitter_for_public(c.latitude, c.longitude, seed=c.id)
        cat = db.get(Category, c.category_id)
        jur = db.get(Jurisdiction, c.jurisdiction_id) if c.jurisdiction_id else None
        age_h = (utcnow() - _aware(c.created_at)).total_seconds() / 3600.0
        markers.append({
            "public_id": c.public_id, "lat": lat, "lng": lng,
            "category": cat.code, "category_name": cat.name_en,
            "status": c.status, "priority_level": c.priority_level,
            "risk_score": round(c.risk_score), "risk_level": c.risk_level,
            "age_hours": round(age_h, 1),
            "jurisdiction": (f"{jur.authority} Ward {jur.ward_number}"
                             if jur and jur.ward_number else (jur.name if jur else None)),
            "jurisdiction_id": jur.id if jur else None,
            "ward": jur.ward_number if jur else None,
        })
    return {"total_in_bounds": total, "returned": len(markers), "markers": markers,
            "location_note": ("Marker positions are approximate. Exact reported "
                              "coordinates are never exposed publicly."),
            "disclaimer": DISCLAIMER}
