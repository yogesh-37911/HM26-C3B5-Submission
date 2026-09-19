"""Jurisdiction resolution + versioned boundary administration."""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..engines.geo import polygon_bbox
from ..models import Jurisdiction, JurisdictionVersion, Role, User, utcnow
from ..schemas import JurisdictionVersionCreate
from ..security import require_roles
from ..services import audit
from ..services import complaint_service as svc

router = APIRouter(prefix="/api/jurisdictions", tags=["jurisdictions"])


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/resolve")
def resolve(lat: float = Query(..., ge=-90, le=90),
            lng: float = Query(..., ge=-180, le=180),
            db: Session = Depends(get_db)):
    """Public: which authority would handle a complaint at this point today?"""
    return svc.route_complaint(db, lat, lng).as_dict()


@router.get("")
def list_jurisdictions(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Jurisdiction).order_by(Jurisdiction.ward_number)))
    return {"items": [{"id": j.id, "authority": j.authority,
                       "authority_type": j.authority_type, "ward": j.ward_number,
                       "name": j.name} for j in rows]}


@router.get("/versions")
def list_versions(jurisdiction_id: int | None = None, active_only: bool = False,
                  db: Session = Depends(get_db)):
    stmt = select(JurisdictionVersion)
    if jurisdiction_id:
        stmt = stmt.where(JurisdictionVersion.jurisdiction_id == jurisdiction_id)
    rows = list(db.scalars(stmt.order_by(JurisdictionVersion.effective_from.desc())))
    now = utcnow()
    out = []
    for v in rows:
        start, end = _aware(v.effective_from), (_aware(v.effective_to) if v.effective_to else None)
        is_active = start <= now and (end is None or now < end)
        if active_only and not is_active:
            continue
        j = db.get(Jurisdiction, v.jurisdiction_id)
        out.append({"id": v.id, "jurisdiction_id": v.jurisdiction_id,
                    "authority": j.authority, "ward": j.ward_number, "name": j.name,
                    "version_label": v.version_label,
                    "effective_from": start.isoformat(),
                    "effective_to": end.isoformat() if end else None,
                    "is_active": is_active, "boundary": v.boundary_json,
                    "source_note": v.source_note})
    return {"items": out, "count": len(out), "as_of": now.isoformat()}


@router.post("/version", status_code=status.HTTP_201_CREATED)
def create_version(body: JurisdictionVersionCreate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.ADMIN))):
    """Publish a new boundary version. Admin only.

    Existing complaints keep the version they were routed under; only new
    complaints are resolved against the newly active boundary.
    """
    j = db.get(Jurisdiction, body.jurisdiction_id)
    if not j:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Jurisdiction not found")

    dup = db.scalar(select(JurisdictionVersion).where(
        JurisdictionVersion.jurisdiction_id == j.id,
        JurisdictionVersion.version_label == body.version_label))
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Version '{body.version_label}' already exists for this jurisdiction")

    if body.close_previous:
        for prev in db.scalars(select(JurisdictionVersion).where(
                JurisdictionVersion.jurisdiction_id == j.id,
                JurisdictionVersion.effective_to.is_(None))):
            prev.effective_to = body.effective_from

    min_lat, max_lat, min_lng, max_lng = polygon_bbox(body.boundary)
    v = JurisdictionVersion(
        jurisdiction_id=j.id, version_label=body.version_label,
        effective_from=body.effective_from, effective_to=body.effective_to,
        boundary_json=body.boundary, min_lat=min_lat, max_lat=max_lat,
        min_lng=min_lng, max_lng=max_lng,
        source_note=body.source_note or
        "Synthetic demonstration boundary published via admin console.")
    db.add(v)
    db.flush()
    audit.record(db, actor=user, action="JURISDICTION_VERSION_CREATE",
                 entity_type="jurisdiction", entity_id=j.id,
                 after={"version": body.version_label,
                        "effective_from": body.effective_from.isoformat()},
                 ip=request.client.host if request.client else None)
    db.commit()
    return {"id": v.id, "jurisdiction_id": j.id, "version_label": v.version_label,
            "effective_from": _aware(v.effective_from).isoformat(),
            "note": "Historical complaints retain their original routing."}
