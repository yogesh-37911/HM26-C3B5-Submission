"""Audit trail for officer/admin actions."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog, User


def record(db: Session, *, actor: User | None, action: str, entity_type: str,
           entity_id: str | int, before: dict | None = None,
           after: dict | None = None, ip: str | None = None) -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action, entity_type=entity_type, entity_id=str(entity_id),
        before=before, after=after, ip=ip,
    ))
