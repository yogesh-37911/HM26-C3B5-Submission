"""Field worker task list and offline sync."""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Assignment,
    Category,
    Complaint,
    ComplaintStatus,
    OfflineSyncQueue,
    Role,
    User,
    utcnow,
)
from ..schemas import OfflineSyncRequest
from ..security import get_current_user, require_roles
from ..services import audit
from ..services import complaint_service as svc

router = APIRouter(prefix="/api/field-worker", tags=["field-worker"])


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _my_assignment(db: Session, task_id: int, user: User) -> tuple[Assignment, Complaint]:
    a = db.get(Assignment, task_id)
    if not a or not a.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    if a.field_worker_id != user.id and user.role != Role.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Task is not assigned to you")
    return a, db.get(Complaint, a.complaint_id)


@router.get("/tasks")
def tasks(db: Session = Depends(get_db),
          user: User = Depends(require_roles(Role.FIELD_WORKER, Role.ADMIN))):
    rows = list(db.scalars(select(Assignment).where(
        Assignment.field_worker_id == user.id, Assignment.is_active.is_(True))))
    out = []
    for a in rows:
        c = db.get(Complaint, a.complaint_id)
        cat = db.get(Category, c.category_id)
        out.append({
            "task_id": a.id, "state": a.state, "public_id": c.public_id,
            "title": c.title, "description": c.description,
            "category": cat.name_en, "category_kn": cat.name_kn,
            "landmark": c.landmark, "latitude": c.latitude, "longitude": c.longitude,
            "priority_level": c.priority_level, "risk_score": round(c.risk_score),
            "status": c.status, "sla": svc.sla_for(db, c),
            "assigned_at": _aware(a.assigned_at).isoformat(),
            "started_at": _aware(a.started_at).isoformat() if a.started_at else None,
        })
    out.sort(key=lambda t: (t["priority_level"] != "CRITICAL", -t["risk_score"]))
    return {"items": out, "count": len(out)}


@router.post("/tasks/{task_id}/start")
def start_task(task_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.FIELD_WORKER, Role.ADMIN))):
    a, c = _my_assignment(db, task_id, user)
    now = utcnow()
    a.started_at = now
    a.state = "IN_PROGRESS"
    if c.status == ComplaintStatus.ASSIGNED.value:
        before = c.status
        c.status = ComplaintStatus.IN_PROGRESS.value
        c.status_change_count += 1
        svc.add_event(db, c, event_type="FIELD_STARTED", from_status=before,
                      to_status=c.status, actor=user,
                      note="Field worker started inspection.", at=now)
    c.last_action_at = now
    svc.recompute_scores(db, c, now=now)
    db.commit()
    return {"ok": True, "status": c.status}


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, note: str = "", resolved: bool = True,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.FIELD_WORKER, Role.ADMIN))):
    a, c = _my_assignment(db, task_id, user)
    now = utcnow()
    a.completed_at = now

    if resolved:
        a.state = "COMPLETED"
        a.is_active = False
        before = c.status
        # Field completion produces FIELD_VERIFIED; only an officer closes a
        # complaint as RESOLVED. Separation of duties.
        c.status = ComplaintStatus.FIELD_VERIFIED.value
        c.status_change_count += 1
        svc.add_event(db, c, event_type="FIELD_VERIFIED", from_status=before,
                      to_status=c.status, actor=user,
                      note=note or "Field worker completed the job and verified on site.",
                      at=now)
        svc.notify(db, c.citizen_id, f"Work completed on {c.public_id}",
                   "A field worker has completed work. Awaiting officer closure.",
                   kind="FIELD_VERIFIED", complaint_id=c.id)
    else:
        a.state = "UNABLE_TO_RESOLVE"
        a.is_active = False
        svc.add_event(db, c, event_type="FIELD_BLOCKED", actor=user,
                      note=note or "Field worker unable to resolve; reassignment requested.",
                      at=now)

    c.last_action_at = now
    svc.recompute_scores(db, c, now=now)
    audit.record(db, actor=user, action="FIELD_COMPLETE", entity_type="complaint",
                 entity_id=c.public_id, after={"resolved": resolved, "note": note})
    db.commit()
    return {"ok": True, "status": c.status, "assignment_state": a.state}


@router.post("/sync")
def sync_offline(body: OfflineSyncRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Replay a device's offline action queue.

    Idempotency keys are the contract: replaying the same queue twice (common
    on a flaky connection where the response is lost) applies each action once.
    """
    applied, skipped, failed = [], [], []
    for action in body.actions:
        existing = db.scalar(select(OfflineSyncQueue).where(
            OfflineSyncQueue.idempotency_key == action.idempotency_key))
        if existing:
            skipped.append({"key": action.idempotency_key,
                            "reason": "Already applied", "ref": existing.result_ref})
            continue
        try:
            ref = _apply_offline_action(db, user, action)
            db.add(OfflineSyncQueue(
                user_id=user.id, idempotency_key=action.idempotency_key,
                action_type=action.action_type, payload=action.payload,
                state="APPLIED", result_ref=ref,
                client_created_at=action.client_created_at))
            applied.append({"key": action.idempotency_key, "ref": ref})
        except HTTPException as exc:
            db.add(OfflineSyncQueue(
                user_id=user.id, idempotency_key=action.idempotency_key,
                action_type=action.action_type, payload=action.payload,
                state="FAILED", result_ref=str(exc.detail),
                client_created_at=action.client_created_at))
            failed.append({"key": action.idempotency_key, "error": str(exc.detail)})
    db.commit()
    return {"applied": len(applied), "skipped": len(skipped), "failed": len(failed),
            "details": {"applied": applied, "skipped": skipped, "failed": failed},
            "message": (f"Synced successfully. {len(applied)} action(s) applied, "
                        f"{len(skipped)} already present.")}


def _apply_offline_action(db: Session, user: User, action) -> str:
    p = action.payload
    if action.action_type == "FIELD_NOTE":
        c = db.scalar(select(Complaint).where(Complaint.public_id == p.get("public_id")))
        if not c:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")
        svc.add_event(db, c, event_type="FIELD_NOTE", actor=user,
                      note=f"[recorded offline] {p.get('note', '')[:300]}",
                      at=action.client_created_at or utcnow())
        c.last_action_at = utcnow()
        return c.public_id
    if action.action_type == "TASK_START":
        a, c = _my_assignment(db, int(p["task_id"]), user)
        a.started_at = action.client_created_at or utcnow()
        a.state = "IN_PROGRESS"
        if c.status == ComplaintStatus.ASSIGNED.value:
            c.status = ComplaintStatus.IN_PROGRESS.value
            c.status_change_count += 1
        svc.add_event(db, c, event_type="FIELD_STARTED", actor=user,
                      note="[recorded offline] Field worker started inspection.",
                      at=a.started_at)
        c.last_action_at = utcnow()
        return c.public_id
    if action.action_type == "TASK_COMPLETE":
        a, c = _my_assignment(db, int(p["task_id"]), user)
        a.completed_at = action.client_created_at or utcnow()
        a.state = "COMPLETED"
        a.is_active = False
        c.status = ComplaintStatus.FIELD_VERIFIED.value
        c.status_change_count += 1
        c.last_action_at = utcnow()
        svc.add_event(db, c, event_type="FIELD_VERIFIED", actor=user,
                      note=f"[recorded offline] {p.get('note', 'Job completed on site.')}",
                      at=a.completed_at)
        svc.recompute_scores(db, c)
        return c.public_id
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Unsupported offline action '{action.action_type}'")
