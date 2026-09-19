from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification, Role, User
from ..schemas import LoginRequest, TokenResponse, UserOut
from ..security import create_access_token, get_current_user, verify_password
from ..services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Constant-ish response: never reveal whether the email exists.
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    audit.record(db, actor=user, action="LOGIN", entity_type="user", entity_id=user.id,
                 ip=request.client.host if request.client else None)
    db.commit()
    return TokenResponse(access_token=create_access_token(user),
                         user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                  unread_only: bool = False):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    rows = list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(50)))
    return {"items": [{"id": n.id, "title": n.title, "body": n.body, "kind": n.kind,
                       "is_read": n.is_read, "complaint_id": n.complaint_id,
                       "at": n.created_at.isoformat()} for n in rows],
            "unread": sum(1 for n in rows if not n.is_read)}


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}


@router.get("/field-workers")
def field_workers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Officers need the roster to assign work."""
    if user.role not in {Role.OFFICER.value, Role.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    stmt = select(User).where(User.role == Role.FIELD_WORKER.value,
                              User.is_active.is_(True))
    if user.role == Role.OFFICER.value and user.jurisdiction_id:
        stmt = stmt.where(User.jurisdiction_id == user.jurisdiction_id)
    return {"items": [{"id": u.id, "full_name": u.full_name, "email": u.email,
                       "jurisdiction_id": u.jurisdiction_id}
                      for u in db.scalars(stmt)]}
