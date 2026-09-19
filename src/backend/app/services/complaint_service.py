"""Orchestration: turns a raw citizen report into a routed, scored complaint.

Every automated decision made here writes an immutable timeline event so the
citizen and the officer can both see WHAT happened, WHY, and on WHAT DATA.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..engines import duplicate as dup_engine
from ..engines import jurisdiction as jur_engine
from ..engines import priority as prio_engine
from ..engines import risk as risk_engine
from ..engines import verification as verify_engine
from ..engines.geo import bbox_for_radius, haversine_m
from ..engines.sla import sla_state
from ..models import (
    Assignment,
    Category,
    Complaint,
    ComplaintEvidence,
    ComplaintStatus,
    ComplaintStatusHistory,
    DuplicateCandidate,
    Jurisdiction,
    JurisdictionVersion,
    Notification,
    PriorityScore,
    RiskScore,
    SLARule,
    User,
    utcnow,
)
from ..reference import SENSITIVE_PLACES


# ---------------------------------------------------------------- utilities
def next_public_id(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.scalar(select(func.count(Complaint.id))) or 0
    return f"CIV-{year}-{count + 1:06d}"


def add_event(db: Session, complaint: Complaint, *, event_type: str,
              note: str, from_status: str | None = None, to_status: str | None = None,
              actor: User | None = None, actor_label: str = "SYSTEM",
              payload: dict | None = None, at: datetime | None = None) -> ComplaintStatusHistory:
    ev = ComplaintStatusHistory(
        complaint_id=complaint.id, event_type=event_type, note=note,
        from_status=from_status, to_status=to_status,
        actor_id=actor.id if actor else None,
        actor_label=actor.email if actor else actor_label,
        payload=payload, created_at=at or utcnow(),
    )
    db.add(ev)
    return ev


def notify(db: Session, user_id: int | None, title: str, body: str,
           kind: str = "INFO", complaint_id: int | None = None) -> None:
    if not user_id:
        return
    db.add(Notification(user_id=user_id, title=title, body=body, kind=kind,
                        complaint_id=complaint_id))


def nearby_sensitive_places(lat: float, lng: float, radius_m: float = 250.0) -> list[dict]:
    out = []
    for p in SENSITIVE_PLACES:
        d = haversine_m(lat, lng, p["lat"], p["lng"])
        if d <= radius_m:
            out.append({"type": p["type"], "name": p["name"], "distance_m": d})
    return sorted(out, key=lambda x: x["distance_m"])


# ------------------------------------------------------------ jurisdiction
def route_complaint(db: Session, lat: float, lng: float,
                    at: datetime | None = None) -> jur_engine.RouteResult:
    """Bounding-box prefilter in SQL, exact containment in Python."""
    at = at or utcnow()
    pad = 0.03  # ~3km padding so nearest-fallback still has candidates
    stmt = select(JurisdictionVersion).where(
        JurisdictionVersion.min_lat <= lat + pad,
        JurisdictionVersion.max_lat >= lat - pad,
        JurisdictionVersion.min_lng <= lng + pad,
        JurisdictionVersion.max_lng >= lng - pad,
    )
    versions = list(db.scalars(stmt))
    if not versions:
        versions = list(db.scalars(select(JurisdictionVersion)))
    jur_ids = {v.jurisdiction_id for v in versions}
    index = {j.id: j for j in db.scalars(
        select(Jurisdiction).where(Jurisdiction.id.in_(jur_ids))
    )} if jur_ids else {}
    return jur_engine.resolve(latitude=lat, longitude=lng, versions=versions,
                              jurisdiction_index=index, at=at)


# --------------------------------------------------------------- duplicates
def find_duplicates(db: Session, *, lat: float, lng: float, text: str,
                    category_id: int, created_at: datetime | None = None,
                    exclude_id: int | None = None, limit: int = 5) -> list[dup_engine.DuplicateMatch]:
    """Category-gated, bbox-prefiltered duplicate search."""
    created_at = created_at or utcnow()
    radius = settings.DUP_RADIUS_M
    window = settings.DUP_TIME_WINDOW_HOURS

    min_lat, max_lat, min_lng, max_lng = bbox_for_radius(lat, lng, radius)
    since = created_at - timedelta(hours=window)

    stmt = select(Complaint).where(
        Complaint.category_id == category_id,          # hard category gate
        Complaint.latitude.between(min_lat, max_lat),  # indexed prefilter
        Complaint.longitude.between(min_lng, max_lng),
        Complaint.created_at >= since,
        Complaint.status != ComplaintStatus.REJECTED.value,
    ).limit(200)
    if exclude_id:
        stmt = stmt.where(Complaint.id != exclude_id)

    matches: list[dup_engine.DuplicateMatch] = []
    for cand in db.scalars(stmt):
        c_created = cand.created_at
        if c_created.tzinfo is None:
            c_created = c_created.replace(tzinfo=timezone.utc)
        ref = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        sim, dist, txt, hrs = dup_engine.score_candidate(
            new_lat=lat, new_lng=lng, new_text=text, new_created_hours_ago=0.0,
            cand_lat=cand.latitude, cand_lng=cand.longitude,
            cand_text=f"{cand.title} {cand.description}",
            cand_created_hours_ago=-(ref - c_created).total_seconds() / 3600.0,
            radius_m=radius, window_hours=window,
        )
        if dist > radius or sim < settings.DUP_MIN_SIMILARITY:
            continue
        matches.append(dup_engine.DuplicateMatch(
            complaint_id=cand.id, public_id=cand.public_id, title=cand.title,
            status=cand.status, distance_m=dist, text_similarity=txt,
            hours_apart=hrs, similarity=sim,
            reason=dup_engine.build_reason(dist, txt, hrs),
        ))
    matches.sort(key=lambda m: m.similarity, reverse=True)
    return matches[:limit]


# ------------------------------------------------------------------ scoring
def _category_and_sla(db: Session, category_id: int) -> tuple[Category, int]:
    cat = db.get(Category, category_id)
    rule = db.scalar(select(SLARule).where(SLARule.category_id == category_id))
    return cat, (rule.target_hours if rule else 72)


def jurisdiction_avg_resolution_hours(db: Session, jurisdiction_id: int | None) -> float | None:
    if not jurisdiction_id:
        return None
    rows = db.execute(
        select(Complaint.created_at, Complaint.resolved_at).where(
            Complaint.jurisdiction_id == jurisdiction_id,
            Complaint.resolved_at.is_not(None),
        ).limit(300)
    ).all()
    if not rows:
        return None
    total = 0.0
    for created, resolved in rows:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=timezone.utc)
        total += (resolved - created).total_seconds() / 3600.0
    return total / len(rows)


def active_assignment(db: Session, complaint_id: int) -> Assignment | None:
    return db.scalar(select(Assignment).where(
        Assignment.complaint_id == complaint_id, Assignment.is_active.is_(True)
    ))


def duplicate_cluster_size(db: Session, complaint: Complaint) -> int:
    if complaint.duplicate_cluster_id:
        return db.scalar(select(func.count(Complaint.id)).where(
            Complaint.duplicate_cluster_id == complaint.duplicate_cluster_id
        )) or 1
    return 1


def recompute_scores(db: Session, complaint: Complaint, *, now: datetime | None = None,
                     persist_history: bool = True) -> tuple[dict, dict]:
    """Recompute priority + risk from current DB state. Returns both payloads."""
    now = now or utcnow()
    cat, sla_hours = _category_and_sla(db, complaint.category_id)
    assignment = active_assignment(db, complaint.id)
    dup_count = max(duplicate_cluster_size(db, complaint) - 1, 0)
    has_evidence = bool(db.scalar(select(func.count(ComplaintEvidence.id)).where(
        ComplaintEvidence.complaint_id == complaint.id)))

    # Recurring location: other complaints within 80m in the last 90 days.
    min_lat, max_lat, min_lng, max_lng = bbox_for_radius(
        complaint.latitude, complaint.longitude, 80)
    recurring = (db.scalar(select(func.count(Complaint.id)).where(
        Complaint.id != complaint.id,
        Complaint.latitude.between(min_lat, max_lat),
        Complaint.longitude.between(min_lng, max_lng),
        Complaint.created_at >= now - timedelta(days=90),
    )) or 0) >= 3

    p = prio_engine.compute_priority(
        base_severity=cat.base_severity, safety_impact=cat.safety_impact,
        nearby_sensitive=nearby_sensitive_places(complaint.latitude, complaint.longitude),
        duplicate_cluster_size=duplicate_cluster_size(db, complaint),
        followup_count=complaint.followup_count, created_at=complaint.created_at,
        sla_target_hours=sla_hours, is_recurring_location=recurring, now=now,
    )
    r = risk_engine.compute_risk(
        created_at=complaint.created_at, last_action_at=complaint.last_action_at,
        status=complaint.status, sla_target_hours=sla_hours,
        category_avg_resolution_hours=cat.historical_avg_resolution_hours,
        jurisdiction_avg_resolution_hours=jurisdiction_avg_resolution_hours(
            db, complaint.jurisdiction_id),
        has_field_worker=assignment is not None,
        status_change_count=complaint.status_change_count,
        duplicate_count=dup_count, followup_count=complaint.followup_count,
        reopen_count=complaint.reopen_count, base_severity=cat.base_severity,
        safety_impact=cat.safety_impact, has_evidence=has_evidence, now=now,
    )

    complaint.priority_score = p.score
    complaint.priority_level = p.level
    complaint.risk_score = r.score
    complaint.risk_level = r.level
    complaint.sla_target_hours = sla_hours
    complaint.sla_due_at = _aware(complaint.created_at) + timedelta(hours=sla_hours)

    if persist_history:
        db.add(PriorityScore(complaint_id=complaint.id, score=p.score, level=p.level,
                             factors=[f.as_dict() for f in p.factors],
                             model_version=p.model_version, computed_at=now))
        db.add(RiskScore(complaint_id=complaint.id, score=r.score, level=r.level,
                         factors=[f.as_dict() for f in r.factors],
                         recommended_action=r.recommended_action,
                         model_version=r.model_version, computed_at=now))
    return p.as_dict(), r.as_dict()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sla_for(db: Session, complaint: Complaint, now: datetime | None = None) -> dict:
    return sla_state(created_at=complaint.created_at,
                     target_hours=complaint.sla_target_hours,
                     resolved_at=complaint.resolved_at,
                     risk_score=complaint.risk_score, now=now)


# ------------------------------------------------------------ verification
def run_verification(db: Session, complaint: Complaint, *, dup_count: int,
                     routed: bool) -> verify_engine.VerificationResult:
    ev_hashes = list(db.scalars(select(ComplaintEvidence.sha256).where(
        ComplaintEvidence.complaint_id == complaint.id)))
    reuse = 0
    for h in ev_hashes:
        reuse = max(reuse, (db.scalar(select(func.count(ComplaintEvidence.id)).where(
            ComplaintEvidence.sha256 == h,
            ComplaintEvidence.complaint_id != complaint.id)) or 0))

    recent = 0
    if complaint.citizen_id:
        recent = db.scalar(select(func.count(Complaint.id)).where(
            Complaint.citizen_id == complaint.citizen_id,
            Complaint.created_at >= _aware(complaint.created_at) - timedelta(hours=1),
            Complaint.id != complaint.id,
        )) or 0

    result = verify_engine.verify_report(
        latitude=complaint.latitude, longitude=complaint.longitude,
        description=complaint.description, title=complaint.title,
        has_evidence=bool(ev_hashes), evidence_hash_reuse_count=reuse,
        submissions_from_user_last_hour=recent, duplicate_count=dup_count,
        inside_known_jurisdiction=routed,
    )
    complaint.verification_status = result.status
    complaint.verification_factors = result.factors
    return result


# ---------------------------------------------------------- full intake flow
def intake(db: Session, complaint: Complaint, *, duplicates: list[dup_engine.DuplicateMatch],
           actor: User | None = None, now: datetime | None = None) -> dict:
    """Run validate -> route -> verify -> prioritise -> predict, writing timeline."""
    now = now or utcnow()

    add_event(db, complaint, event_type="SUBMITTED", note="Complaint submitted by citizen.",
              to_status=ComplaintStatus.SUBMITTED.value, actor=actor, at=now)

    # Route
    route = route_complaint(db, complaint.latitude, complaint.longitude, at=now)
    complaint.jurisdiction_id = route.jurisdiction_id
    complaint.jurisdiction_version_id = route.jurisdiction_version_id
    complaint.routing_confidence = route.confidence
    complaint.routing_reason = route.reason
    add_event(db, complaint, event_type="ROUTED",
              note=f"Routed to {route.authority}"
                   + (f" Ward {route.ward_number}" if route.ward_number else "")
                   + f" (boundary version {route.version_label})."
              if route.jurisdiction_id else "Automatic routing failed; queued for manual routing.",
              from_status=ComplaintStatus.SUBMITTED.value,
              to_status=ComplaintStatus.ROUTED.value if route.jurisdiction_id
              else ComplaintStatus.VALIDATING.value,
              payload=route.as_dict(), at=now)
    complaint.status = (ComplaintStatus.ROUTED.value if route.jurisdiction_id
                        else ComplaintStatus.VALIDATING.value)
    complaint.status_change_count += 1

    # Verify
    ver = run_verification(db, complaint, dup_count=len(duplicates),
                           routed=route.jurisdiction_id is not None)
    add_event(db, complaint, event_type="VERIFIED",
              note=f"Verification: {ver.status} (confidence {ver.confidence}%).",
              payload=ver.as_dict(), at=now)

    # Duplicates
    if duplicates:
        for m in duplicates:
            db.add(DuplicateCandidate(
                complaint_id=complaint.id, candidate_complaint_id=m.complaint_id,
                similarity=m.similarity, distance_m=m.distance_m,
                text_similarity=m.text_similarity, hours_apart=m.hours_apart,
            ))
        add_event(db, complaint, event_type="DUPLICATE_CHECK",
                  note=f"{len(duplicates)} possible duplicate(s) detected. "
                       "Report retained as a separate record pending review.",
                  payload={"candidates": [m.as_dict() for m in duplicates]}, at=now)

    db.flush()
    priority, risk = recompute_scores(db, complaint, now=now)
    add_event(db, complaint, event_type="PRIORITY_CALCULATED",
              note=f"Priority calculated: {priority['priority_level']} "
                   f"({priority['priority_score']}/100).",
              payload=priority, at=now)
    add_event(db, complaint, event_type="RISK_CALCULATED",
              note=f"Neglect risk: {risk['risk_score']}/100 ({risk['risk_level']}).",
              payload=risk, at=now)

    if complaint.citizen_id:
        notify(db, complaint.citizen_id,
               f"Complaint {complaint.public_id} registered",
               f"Routed to {route.authority}. Priority {priority['priority_level']}. "
               f"Expected resolution within {complaint.sla_target_hours}h.",
               kind="COMPLAINT_CREATED", complaint_id=complaint.id)

    return {"routing": route.as_dict(), "verification": ver.as_dict(),
            "priority": priority, "risk": risk,
            "duplicates": [m.as_dict() for m in duplicates]}
