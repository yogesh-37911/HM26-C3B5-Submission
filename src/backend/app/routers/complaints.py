from __future__ import annotations

import hashlib
import os
from datetime import timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    ALLOWED_TRANSITIONS,
    Assignment,
    Category,
    Complaint,
    ComplaintEvidence,
    ComplaintFollowup,
    ComplaintStatus,
    DuplicateCandidate,
    DuplicateCluster,
    Jurisdiction,
    JurisdictionVersion,
    Role,
    User,
    utcnow,
)
from ..schemas import (
    AssignRequest,
    ComplaintCreate,
    DuplicateCheckRequest,
    FollowupRequest,
    StatusChangeRequest,
)
from ..engines.geo import jitter_for_public
from ..security import assert_jurisdiction_access, get_current_user, get_optional_user, require_roles
from ..services import audit
from ..services import complaint_service as svc

router = APIRouter(prefix="/api/complaints", tags=["complaints"])

SORTABLE = {
    "risk": Complaint.risk_score, "priority": Complaint.priority_score,
    "age": Complaint.created_at, "sla": Complaint.sla_due_at,
    "category": Complaint.category_id, "created_at": Complaint.created_at,
}


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def complaint_summary(db: Session, c: Complaint, *, include_private: bool) -> dict:
    cat = db.get(Category, c.category_id)
    jur = db.get(Jurisdiction, c.jurisdiction_id) if c.jurisdiction_id else None
    age_h = (utcnow() - _aware(c.created_at)).total_seconds() / 3600.0
    out = {
        "id": c.id, "public_id": c.public_id, "title": c.title,
        "category": {"code": cat.code, "name_en": cat.name_en, "name_kn": cat.name_kn},
        "status": c.status, "verification_status": c.verification_status,
        "priority_level": c.priority_level, "priority_score": round(c.priority_score),
        "risk_level": c.risk_level, "risk_score": round(c.risk_score),
        "age_hours": round(age_h, 1),
        "ward": jur.ward_number if jur else None,
        "authority": jur.authority if jur else None,
        "jurisdiction_name": jur.name if jur else None,
        "created_at": _aware(c.created_at).isoformat(),
        "last_action_at": _aware(c.last_action_at).isoformat(),
        "sla": svc.sla_for(db, c),
        "is_synthetic": c.is_synthetic,
        "assigned": svc.active_assignment(db, c.id) is not None,
    }
    if include_private:
        out.update({"latitude": c.latitude, "longitude": c.longitude,
                    "description": c.description, "landmark": c.landmark,
                    "citizen_id": c.citizen_id})
    else:
        # Public surfaces never receive the exact reported coordinate or the
        # reporter's identity. The offset is deterministic per complaint id so
        # markers stay put between loads, but the true point is not recoverable.
        lat, lng = jitter_for_public(c.latitude, c.longitude, seed=c.id)
        out.update({"latitude": lat, "longitude": lng, "approximate_location": True})
    return out


# ---------------------------------------------------------------- duplicates
@router.post("/check-duplicates")
def check_duplicates(body: DuplicateCheckRequest, db: Session = Depends(get_db)):
    """Pre-submission duplicate probe. Called live from the citizen form."""
    cat = db.scalar(select(Category).where(Category.code == body.category_code))
    if not cat:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown category")
    matches = svc.find_duplicates(
        db, lat=body.latitude, lng=body.longitude,
        text=f"{body.title} {body.description}", category_id=cat.id)
    return {
        "possible_duplicate": bool(matches),
        "matches": [m.as_dict() for m in matches],
        "note": ("Possible duplicates are surfaced for the citizen to confirm. "
                 "No report is ever discarded automatically."),
    }


# ------------------------------------------------------------------- create
@router.post("", status_code=status.HTTP_201_CREATED)
def create_complaint(body: ComplaintCreate, request: Request,
                     db: Session = Depends(get_db),
                     user: User | None = Depends(get_optional_user)):
    # Idempotency: an offline device replaying its queue must not double-file.
    if body.idempotency_key:
        existing = db.scalar(select(Complaint).where(
            Complaint.idempotency_key == body.idempotency_key))
        if existing:
            return {"complaint": complaint_summary(db, existing, include_private=True),
                    "deduplicated_by_idempotency_key": True,
                    "analysis": {"note": "Replay of an already-accepted submission."}}

    cat = db.scalar(select(Category).where(Category.code == body.category_code))
    if not cat:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Unknown category '{body.category_code}'")

    created_at = utcnow()
    matches = svc.find_duplicates(
        db, lat=body.latitude, lng=body.longitude,
        text=f"{body.title} {body.description}", category_id=cat.id,
        created_at=created_at)

    c = Complaint(
        public_id=svc.next_public_id(db),
        citizen_id=user.id if user and user.role == Role.CITIZEN.value else None,
        category_id=cat.id, title=body.title, description=body.description,
        landmark=body.landmark, latitude=body.latitude, longitude=body.longitude,
        idempotency_key=body.idempotency_key,
        source_channel="OFFLINE_SYNC" if body.client_created_at else "WEB",
        created_at=created_at, last_action_at=created_at,
    )
    db.add(c)
    db.flush()

    # Duplicate clustering: join the strongest match's cluster, or open one.
    if matches:
        top = matches[0]
        primary = db.get(Complaint, top.complaint_id)
        if primary.duplicate_cluster_id:
            cluster = db.get(DuplicateCluster, primary.duplicate_cluster_id)
        else:
            cluster = DuplicateCluster(
                primary_complaint_id=primary.id, category_id=cat.id,
                centroid_lat=primary.latitude, centroid_lng=primary.longitude,
                member_count=1)
            db.add(cluster)
            db.flush()
            primary.duplicate_cluster_id = cluster.id
        cluster.member_count += 1
        c.duplicate_cluster_id = cluster.id

    analysis = svc.intake(db, c, duplicates=matches, actor=user, now=created_at)
    db.commit()

    return {"complaint": complaint_summary(db, c, include_private=True),
            "analysis": analysis}


# --------------------------------------------------------------------- list
@router.get("")
def list_complaints(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    ward: int | None = None,
    risk_level: str | None = None,
    priority_level: str | None = None,
    unassigned: bool | None = None,
    sla_breached: bool | None = None,
    sort: str = Query("risk"),
    order: str = Query("desc"),
    mine: bool = False,
):
    stmt = select(Complaint)

    # --- authorisation scoping, applied before any user filter ---
    if user.role == Role.CITIZEN.value:
        stmt = stmt.where(Complaint.citizen_id == user.id)
    elif user.role == Role.OFFICER.value and user.jurisdiction_id:
        stmt = stmt.where(Complaint.jurisdiction_id == user.jurisdiction_id)
    elif user.role == Role.FIELD_WORKER.value:
        ids = select(Assignment.complaint_id).where(
            Assignment.field_worker_id == user.id, Assignment.is_active.is_(True))
        stmt = stmt.where(Complaint.id.in_(ids))
    if mine and user.role == Role.CITIZEN.value:
        stmt = stmt.where(Complaint.citizen_id == user.id)

    if status_filter:
        stmt = stmt.where(Complaint.status.in_(status_filter.split(",")))
    if category:
        cat = db.scalar(select(Category).where(Category.code == category))
        stmt = stmt.where(Complaint.category_id == (cat.id if cat else -1))
    if ward is not None:
        jids = select(Jurisdiction.id).where(Jurisdiction.ward_number == ward)
        stmt = stmt.where(Complaint.jurisdiction_id.in_(jids))
    if risk_level:
        stmt = stmt.where(Complaint.risk_level == risk_level)
    if priority_level:
        stmt = stmt.where(Complaint.priority_level == priority_level)
    if unassigned:
        assigned = select(Assignment.complaint_id).where(Assignment.is_active.is_(True))
        stmt = stmt.where(Complaint.id.not_in(assigned))
    if sla_breached:
        stmt = stmt.where(Complaint.sla_due_at < utcnow(),
                          Complaint.status.not_in(["RESOLVED", "REJECTED"]))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTABLE.get(sort, Complaint.risk_score)
    stmt = stmt.order_by(desc(col) if order == "desc" else col)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = list(db.scalars(stmt))
    return {
        "total": total, "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "items": [complaint_summary(db, c, include_private=True) for c in rows],
    }


# ------------------------------------------------------------------- detail
def _load_and_authorise(db: Session, ident: str, user: User) -> Complaint:
    c = db.scalar(select(Complaint).where(Complaint.public_id == ident))
    if c is None and ident.isdigit():
        c = db.get(Complaint, int(ident))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")

    # Object-level authorisation on the loaded row (IDOR guard).
    if user.role == Role.CITIZEN.value and c.citizen_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your complaint")
    if user.role == Role.OFFICER.value:
        assert_jurisdiction_access(user, c.jurisdiction_id)
    if user.role == Role.FIELD_WORKER.value:
        a = svc.active_assignment(db, c.id)
        if not a or a.field_worker_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Complaint not assigned to you")
    return c


@router.get("/{ident}")
def get_complaint(ident: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    base = complaint_summary(db, c, include_private=True)

    latest_risk = db.scalar(select(svc.RiskScore).where(
        svc.RiskScore.complaint_id == c.id).order_by(desc(svc.RiskScore.computed_at)))
    latest_prio = db.scalar(select(svc.PriorityScore).where(
        svc.PriorityScore.complaint_id == c.id).order_by(desc(svc.PriorityScore.computed_at)))

    dups = db.scalars(select(DuplicateCandidate).where(
        DuplicateCandidate.complaint_id == c.id)).all()
    jv = db.get(JurisdictionVersion, c.jurisdiction_version_id) if c.jurisdiction_version_id else None

    base.update({
        "verification": {"verification_status": c.verification_status,
                         "verification_factors": c.verification_factors,
                         "disclaimer": svc.verify_engine.DISCLAIMER},
        "risk_explanation": {
            "risk_score": round(latest_risk.score), "risk_level": latest_risk.level,
            "risk_factors": latest_risk.factors,
            "recommended_action": latest_risk.recommended_action,
            "model_version": latest_risk.model_version,
        } if latest_risk else None,
        "priority_explanation": {
            "priority_score": round(latest_prio.score), "priority_level": latest_prio.level,
            "priority_factors": latest_prio.factors,
            "model_version": latest_prio.model_version,
        } if latest_prio else None,
        "jurisdiction": {
            "authority": base["authority"], "ward": base["ward"],
            "boundary_version": jv.version_label if jv else None,
            "effective_from": _aware(jv.effective_from).isoformat() if jv else None,
            "confidence_pct": round((c.routing_confidence or 0) * 100),
            "reason": c.routing_reason,
            "note": ("This complaint retains the boundary version active when it "
                     "was filed, even if ward boundaries have since changed."),
        },
        "duplicates": [{
            "complaint_id": d.candidate_complaint_id,
            "public_id": (db.get(Complaint, d.candidate_complaint_id).public_id
                          if db.get(Complaint, d.candidate_complaint_id) else None),
            "similarity_pct": round(d.similarity * 100),
            "distance_m": round(d.distance_m),
            "decision": d.decision,
        } for d in dups],
        "evidence": [{"id": e.id, "filename": e.filename, "sha256": e.sha256,
                      "size_bytes": e.size_bytes, "stage": e.stage,
                      "url": f"/api/complaints/{c.public_id}/evidence/{e.id}",
                      "created_at": _aware(e.created_at).isoformat()}
                     for e in c.evidence],
        "timeline": [{
            "id": h.id, "event_type": h.event_type, "note": h.note,
            "from_status": h.from_status, "to_status": h.to_status,
            "actor": h.actor_label, "payload": h.payload,
            "at": _aware(h.created_at).isoformat(),
        } for h in c.history],
        "followups": [{"id": f.id, "message": f.message, "kind": f.kind,
                       "at": _aware(f.created_at).isoformat()}
                      for f in db.scalars(select(ComplaintFollowup).where(
                          ComplaintFollowup.complaint_id == c.id))],
    })
    return base


@router.get("/{ident}/risk")
def get_risk(ident: str, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    _, risk = svc.recompute_scores(db, c, persist_history=False)
    db.commit()
    return risk


@router.get("/{ident}/duplicates")
def get_duplicates(ident: str, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    matches = svc.find_duplicates(db, lat=c.latitude, lng=c.longitude,
                                  text=f"{c.title} {c.description}",
                                  category_id=c.category_id, exclude_id=c.id)
    return {"matches": [m.as_dict() for m in matches]}


@router.get("/{ident}/jurisdiction")
def get_jurisdiction(ident: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    historical = db.get(JurisdictionVersion, c.jurisdiction_version_id) if c.jurisdiction_version_id else None
    current = svc.route_complaint(db, c.latitude, c.longitude)
    return {
        "as_filed": {
            "authority": (db.get(Jurisdiction, c.jurisdiction_id).authority
                          if c.jurisdiction_id else None),
            "ward": (db.get(Jurisdiction, c.jurisdiction_id).ward_number
                     if c.jurisdiction_id else None),
            "boundary_version": historical.version_label if historical else None,
            "confidence_pct": round((c.routing_confidence or 0) * 100),
            "reason": c.routing_reason,
        },
        "if_filed_today": current.as_dict(),
        "boundary_changed": (historical is not None
                             and current.jurisdiction_version_id != historical.id),
        "note": ("Historical routing is immutable. Only new complaints use the "
                 "currently active boundary version."),
    }


# ------------------------------------------------------------------ actions
@router.patch("/{ident}/status")
def change_status(ident: str, body: StatusChangeRequest, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OFFICER, Role.ADMIN,
                                                     Role.FIELD_WORKER))):
    c = _load_and_authorise(db, ident, user)
    try:
        target = ComplaintStatus(body.to_status)
        current = ComplaintStatus(c.status)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status value")

    if target not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Illegal transition {current.value} -> {target.value}. "
            f"Allowed: {sorted(s.value for s in ALLOWED_TRANSITIONS[current])}")

    before = c.status
    now = utcnow()
    c.status = target.value
    c.status_change_count += 1
    c.last_action_at = now
    if target == ComplaintStatus.RESOLVED:
        c.resolved_at = now
    if target == ComplaintStatus.REOPENED:
        c.reopen_count += 1
        c.resolved_at = None

    svc.add_event(db, c, event_type="STATUS_CHANGE", from_status=before,
                  to_status=target.value, actor=user,
                  note=body.note or f"Status changed to {target.value}.", at=now)
    svc.recompute_scores(db, c, now=now)
    audit.record(db, actor=user, action="STATUS_CHANGE", entity_type="complaint",
                 entity_id=c.public_id, before={"status": before},
                 after={"status": c.status}, ip=request.client.host if request.client else None)
    svc.notify(db, c.citizen_id, f"Complaint {c.public_id} is now {target.value}",
               body.note or f"Your complaint moved from {before} to {target.value}.",
               kind="STATUS_CHANGE", complaint_id=c.id)
    db.commit()
    return complaint_summary(db, c, include_private=True)


@router.post("/{ident}/assign")
def assign(ident: str, body: AssignRequest, request: Request,
           db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OFFICER, Role.ADMIN))):
    c = _load_and_authorise(db, ident, user)
    worker = db.get(User, body.field_worker_id)
    if not worker or worker.role != Role.FIELD_WORKER.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Not a field worker")

    now = utcnow()
    prev = svc.active_assignment(db, c.id)
    if prev:
        prev.is_active = False
        prev.state = "REASSIGNED"

    db.add(Assignment(complaint_id=c.id, field_worker_id=worker.id,
                      assigned_by_id=user.id, note=body.note, assigned_at=now))
    if c.status in {ComplaintStatus.ROUTED.value, ComplaintStatus.REOPENED.value,
                    ComplaintStatus.SUBMITTED.value, ComplaintStatus.VALIDATING.value}:
        before = c.status
        c.status = ComplaintStatus.ASSIGNED.value
        c.status_change_count += 1
        svc.add_event(db, c, event_type="ASSIGNED", from_status=before,
                      to_status=c.status, actor=user,
                      note=f"Assigned to field worker {worker.full_name}.", at=now)
    else:
        svc.add_event(db, c, event_type="ASSIGNED", actor=user,
                      note=f"Reassigned to field worker {worker.full_name}.", at=now)

    c.last_action_at = now
    db.flush()
    svc.recompute_scores(db, c, now=now)
    audit.record(db, actor=user, action="ASSIGN", entity_type="complaint",
                 entity_id=c.public_id, after={"field_worker_id": worker.id},
                 ip=request.client.host if request.client else None)
    svc.notify(db, worker.id, f"New task: {c.public_id}",
               f"{c.title} - priority {c.priority_level}.", kind="ASSIGNMENT",
               complaint_id=c.id)
    svc.notify(db, c.citizen_id, f"Complaint {c.public_id} assigned",
               "A field worker has been assigned to your complaint.",
               kind="ASSIGNMENT", complaint_id=c.id)
    db.commit()
    return complaint_summary(db, c, include_private=True)


@router.post("/{ident}/followup")
def add_followup(ident: str, body: FollowupRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    now = utcnow()
    db.add(ComplaintFollowup(complaint_id=c.id, user_id=user.id,
                             message=body.message, kind=body.kind, created_at=now))
    c.followup_count += 1
    svc.add_event(db, c, event_type="FOLLOWUP", actor=user,
                  note=f"Citizen follow-up: {body.message[:180]}", at=now)
    # A follow-up is citizen pressure, not officer action: it must NOT reset
    # last_action_at, or chasing a complaint would lower its neglect risk.
    svc.recompute_scores(db, c, now=now)
    db.commit()
    return {"ok": True, "followup_count": c.followup_count,
            "risk_score": round(c.risk_score), "risk_level": c.risk_level}


@router.post("/{ident}/reopen")
def reopen(ident: str, body: FollowupRequest, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    if c.status != ComplaintStatus.RESOLVED.value:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Only a RESOLVED complaint can be reopened.")
    now = utcnow()
    before = c.status
    c.status = ComplaintStatus.REOPENED.value
    c.reopen_count += 1
    c.status_change_count += 1
    c.resolved_at = None
    c.last_action_at = now
    db.add(ComplaintFollowup(complaint_id=c.id, user_id=user.id,
                             message=body.message, kind="REOPEN_REQUEST", created_at=now))
    svc.add_event(db, c, event_type="REOPENED", from_status=before, to_status=c.status,
                  actor=user, note=f"Citizen reports the issue is not resolved: {body.message[:180]}",
                  at=now)
    svc.recompute_scores(db, c, now=now)
    db.commit()
    return complaint_summary(db, c, include_private=True)


def _generate_demo_evidence_svg(public_id: str, filename: str, stage: str, created_at) -> str:
    stage_upper = (stage or "REPORT").upper()
    stage_label = "FIELD VERIFICATION" if stage_upper == "FIELD" else "CITIZEN REPORT"
    date_str = str(created_at)[:19] if created_at else "Demonstration record"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="100%" height="100%">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#121D18" />
      <stop offset="100%" stop-color="#1E332B" />
    </linearGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#grid)"/>
  <g transform="translate(400, 180)">
    <circle r="56" fill="rgba(20, 102, 85, 0.4)" stroke="#1F7A65" stroke-width="2"/>
    <path d="M -22 -10 L -14 -18 L 14 -18 L 22 -10 L 28 -10 C 32 -10 34 -8 34 -4 L 34 22 C 34 26 32 28 28 28 L -28 28 C -32 28 -34 26 -34 22 L -34 -4 C -34 -8 -32 -10 -28 -10 Z" fill="none" stroke="#68D391" stroke-width="3" stroke-linejoin="round"/>
    <circle cx="0" cy="9" r="12" fill="none" stroke="#68D391" stroke-width="3"/>
    <circle cx="20" cy="-2" r="3" fill="#68D391"/>
  </g>
  <text x="400" y="275" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="20" font-weight="bold" fill="#F7FAFC" text-anchor="middle">
    {stage_label} EVIDENCE
  </text>
  <text x="400" y="305" font-family="'JetBrains Mono', 'SF Mono', Consolas, monospace" font-size="15" fill="#BEE3F8" text-anchor="middle">
    {public_id} &bull; {filename}
  </text>
  <text x="400" y="335" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" fill="#A0AEC0" text-anchor="middle">
    Simulated Demonstration Photo &bull; Recorded: {date_str}
  </text>
  <rect x="250" y="370" width="300" height="32" rx="16" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)"/>
  <text x="400" y="391" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="12" fill="#E2E8F0" text-anchor="middle">
    CivicPulse Synthetic Evidence Artifact
  </text>
</svg>"""


@router.get("/{ident}/evidence/{evidence_id}")
def get_evidence(ident: str, evidence_id: int,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    ev = db.scalar(select(ComplaintEvidence).where(
        ComplaintEvidence.id == evidence_id,
        ComplaintEvidence.complaint_id == c.id,
    ))
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")

    if ev.stored_path and os.path.exists(ev.stored_path):
        return FileResponse(ev.stored_path, media_type=ev.mime_type, filename=ev.filename)

    svg_data = _generate_demo_evidence_svg(c.public_id, ev.filename, ev.stage, ev.created_at)
    return Response(content=svg_data, media_type="image/svg+xml")


@router.post("/{ident}/evidence")
async def upload_evidence(ident: str, file: UploadFile = File(...),
                          stage: str = Query("REPORT"),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)

    stage_clean = (stage or "REPORT").upper()
    if stage_clean not in {"REPORT", "FIELD"}:
        stage_clean = "REPORT"

    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in settings.ALLOWED_MIME:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"Allowed types: {', '.join(settings.ALLOWED_MIME)}")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Maximum size is {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    # Magic-byte check: do not trust the client's declared content type.
    if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "File content is not a valid JPEG, PNG or WEBP image.")

    digest = hashlib.sha256(data).hexdigest()
    reuse = db.scalar(select(func.count(ComplaintEvidence.id)).where(
        ComplaintEvidence.sha256 == digest)) or 0

    os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)
    # Filename is derived from the hash: no path traversal from user input.
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    stored = os.path.join(settings.EVIDENCE_DIR, f"{digest}{ext}")
    if not os.path.exists(stored):
        with open(stored, "wb") as fh:
            fh.write(data)

    ev = ComplaintEvidence(
        complaint_id=c.id, filename=os.path.basename(file.filename or "upload"),
        stored_path=stored, mime_type=content_type, size_bytes=len(data),
        sha256=digest, uploaded_by_id=user.id, stage=stage_clean)
    db.add(ev)
    c.last_action_at = utcnow()
    db.flush()

    svc.add_event(db, c, event_type="EVIDENCE_ADDED", actor=user,
                  note=f"{stage_clean.title()} evidence uploaded ({len(data) // 1024} KB).",
                  payload={"sha256": digest, "hash_reuse_count": reuse})
    if reuse:
        svc.add_event(db, c, event_type="EVIDENCE_FLAGGED", actor=None,
                      note=(f"Repeated evidence detected: this exact image already "
                            f"appears on {reuse} other report(s). Flagged for review, "
                            "not rejected."),
                      payload={"sha256": digest, "reuse_count": reuse})
    svc.run_verification(db, c, dup_count=0, routed=c.jurisdiction_id is not None)
    svc.recompute_scores(db, c)
    db.commit()
    return {"id": ev.id, "sha256": digest, "size_bytes": len(data),
            "hash_reuse_count": reuse,
            "url": f"/api/complaints/{c.public_id}/evidence/{ev.id}",
            "verification_status": c.verification_status,
            "flag": "REPEATED_EVIDENCE" if reuse else None}


@router.delete("/{ident}/evidence/{evidence_id}")
def delete_evidence(ident: str, evidence_id: int, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    c = _load_and_authorise(db, ident, user)
    ev = db.scalar(select(ComplaintEvidence).where(
        ComplaintEvidence.id == evidence_id,
        ComplaintEvidence.complaint_id == c.id,
    ))
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")

    # Authorisation rules:
    # 1. Admin can delete any evidence.
    # 2. Citizen can delete evidence they uploaded if complaint is not resolved/rejected.
    # 3. Officer/Field worker can delete evidence for their jurisdiction or uploaded by them.
    can_delete = False
    if user.role == Role.ADMIN.value:
        can_delete = True
    elif user.role == Role.CITIZEN.value:
        if ev.uploaded_by_id == user.id and c.status not in {"RESOLVED", "REJECTED"}:
            can_delete = True
    elif user.role in {Role.OFFICER.value, Role.FIELD_WORKER.value}:
        if ev.uploaded_by_id == user.id or user.role == Role.OFFICER.value:
            can_delete = True

    if not can_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to delete this evidence record.")

    # Remove physical file if on disk and not referenced by other evidence
    if ev.stored_path and os.path.exists(ev.stored_path):
        other_uses = db.scalar(select(func.count(ComplaintEvidence.id)).where(
            ComplaintEvidence.sha256 == ev.sha256,
            ComplaintEvidence.id != ev.id,
        )) or 0
        if other_uses == 0:
            try:
                os.remove(ev.stored_path)
            except OSError:
                pass

    filename_saved = ev.filename
    stage_saved = ev.stage
    db.delete(ev)
    c.last_action_at = utcnow()
    svc.add_event(db, c, event_type="EVIDENCE_REMOVED", actor=user,
                  note=f"Evidence '{filename_saved}' ({stage_saved}) was removed.",
                  payload={"evidence_id": evidence_id, "filename": filename_saved})
    audit.record(db, actor=user, action="DELETE_EVIDENCE", entity_type="evidence",
                 entity_id=str(evidence_id), before={"filename": filename_saved, "stage": stage_saved},
                 ip=request.client.host if request.client else None)
    db.commit()
    return {"success": True, "deleted_id": evidence_id}

