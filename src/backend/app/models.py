"""Relational schema for Mysuru CivicPulse.

Design notes
------------
* Jurisdiction is *versioned*. A `Jurisdiction` is a stable authority+ward
  identity; a `JurisdictionVersion` carries the boundary geometry valid for a
  date range. A complaint stores BOTH `jurisdiction_id` and the
  `jurisdiction_version_id` that was active when it was routed, so boundary
  changes never rewrite history.
* Risk and priority are stored as first-class rows (not columns on complaint)
  so we retain the full explanation payload and can recompute over time.
* No PostGIS dependency: lat/lng are indexed floats, filtered by bounding box
  then refined with Haversine. See docs/limitations.md.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Enumerations (stored as strings for readability in the DB)
# --------------------------------------------------------------------------
class Role(str, enum.Enum):
    CITIZEN = "CITIZEN"
    OFFICER = "OFFICER"
    FIELD_WORKER = "FIELD_WORKER"
    ADMIN = "ADMIN"


class ComplaintStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    VALIDATING = "VALIDATING"
    ROUTED = "ROUTED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    FIELD_VERIFIED = "FIELD_VERIFIED"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    REJECTED = "REJECTED"


TERMINAL_STATUSES = {ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED}

#: Allowed state machine transitions. Enforced server-side.
ALLOWED_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {
    ComplaintStatus.SUBMITTED: {ComplaintStatus.VALIDATING, ComplaintStatus.ROUTED,
                                ComplaintStatus.REJECTED},
    ComplaintStatus.VALIDATING: {ComplaintStatus.ROUTED, ComplaintStatus.REJECTED},
    ComplaintStatus.ROUTED: {ComplaintStatus.ASSIGNED, ComplaintStatus.REJECTED},
    ComplaintStatus.ASSIGNED: {ComplaintStatus.IN_PROGRESS, ComplaintStatus.ROUTED,
                               ComplaintStatus.REJECTED},
    ComplaintStatus.IN_PROGRESS: {ComplaintStatus.FIELD_VERIFIED,
                                  ComplaintStatus.ASSIGNED,
                                  ComplaintStatus.RESOLVED},
    ComplaintStatus.FIELD_VERIFIED: {ComplaintStatus.RESOLVED,
                                     ComplaintStatus.IN_PROGRESS},
    ComplaintStatus.RESOLVED: {ComplaintStatus.REOPENED},
    ComplaintStatus.REOPENED: {ComplaintStatus.ASSIGNED, ComplaintStatus.ROUTED,
                               ComplaintStatus.IN_PROGRESS},
    ComplaintStatus.REJECTED: {ComplaintStatus.REOPENED},
}


class VerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    PLAUSIBLE = "PLAUSIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SUSPICIOUS = "SUSPICIOUS"


class PriorityLevel(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RiskLevel(str, enum.Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Officers/field workers are scoped to a jurisdiction for RBAC.
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=True, index=True
    )
    device_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Jurisdiction (versioned)
# --------------------------------------------------------------------------
class Jurisdiction(Base):
    """Stable identity of an authority + ward. Geometry lives on versions."""

    __tablename__ = "jurisdictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    authority: Mapped[str] = mapped_column(String(120), index=True)  # e.g. MCC
    authority_type: Mapped[str] = mapped_column(String(40))  # MUNICIPAL / PANCHAYAT / PARASTATAL
    ward_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    contact_email: Mapped[str | None] = mapped_column(String(160), nullable=True)

    versions: Mapped[list["JurisdictionVersion"]] = relationship(
        back_populates="jurisdiction", cascade="all, delete-orphan"
    )


class JurisdictionVersion(Base):
    """A boundary definition valid over a date range.

    Boundary is stored as a GeoJSON-style polygon ring in `boundary_json`
    (list of [lat, lng]) plus a cached bounding box for cheap prefiltering.
    """

    __tablename__ = "jurisdiction_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    jurisdiction_id: Mapped[int] = mapped_column(
        ForeignKey("jurisdictions.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(32))  # e.g. "2026-01"
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    boundary_json: Mapped[list] = mapped_column(JSON)
    min_lat: Mapped[float] = mapped_column(Float, index=True)
    max_lat: Mapped[float] = mapped_column(Float, index=True)
    min_lng: Mapped[float] = mapped_column(Float, index=True)
    max_lng: Mapped[float] = mapped_column(Float, index=True)
    source_note: Mapped[str] = mapped_column(
        Text, default="Synthetic demonstration boundary - not authoritative GIS data."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jurisdiction: Mapped[Jurisdiction] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("jurisdiction_id", "version_label", name="uq_jv_label"),
        Index("ix_jv_bbox", "min_lat", "max_lat", "min_lng", "max_lng"),
    )


# --------------------------------------------------------------------------
# Taxonomy & SLA
# --------------------------------------------------------------------------
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_kn: Mapped[str] = mapped_column(String(160))
    #: 1-5 intrinsic severity used by the priority engine.
    base_severity: Mapped[int] = mapped_column(Integer, default=3)
    #: Does this category carry a direct public-safety hazard?
    safety_impact: Mapped[int] = mapped_column(Integer, default=0)  # 0-3
    #: Rolling historical mean resolution hours; recomputed by seed/analytics.
    historical_avg_resolution_hours: Mapped[float] = mapped_column(Float, default=48.0)


class SLARule(Base):
    """DEMONSTRATION SLA targets. Not official MCC policy."""

    __tablename__ = "sla_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    target_hours: Mapped[int] = mapped_column(Integer)
    is_demo_value: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(
        Text, default="Configurable demonstration SLA for Mysuru CivicPulse; not MCC policy."
    )


# --------------------------------------------------------------------------
# Complaints
# --------------------------------------------------------------------------
class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # CIV-2026-001024
    citizen_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)

    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    landmark: Mapped[str | None] = mapped_column(String(180), nullable=True)

    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)

    status: Mapped[str] = mapped_column(
        String(20), default=ComplaintStatus.SUBMITTED.value, index=True
    )
    verification_status: Mapped[str] = mapped_column(
        String(20), default=VerificationStatus.NEEDS_REVIEW.value, index=True
    )
    verification_factors: Mapped[list] = mapped_column(JSON, default=list)

    # Jurisdiction snapshot at routing time -> history is immutable.
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=True, index=True
    )
    jurisdiction_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("jurisdiction_versions.id"), nullable=True, index=True
    )
    routing_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    duplicate_cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("duplicate_clusters.id"), nullable=True, index=True
    )
    is_duplicate_of: Mapped[int | None] = mapped_column(
        ForeignKey("complaints.id"), nullable=True, index=True
    )

    # Caches of the latest computed scores, for cheap sorting/paging.
    priority_level: Mapped[str] = mapped_column(
        String(12), default=PriorityLevel.MEDIUM.value, index=True
    )
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    risk_level: Mapped[str] = mapped_column(String(12), default=RiskLevel.LOW.value, index=True)

    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    status_change_count: Mapped[int] = mapped_column(Integer, default=0)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)

    sla_target_hours: Mapped[int] = mapped_column(Integer, default=72)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    #: Client-supplied idempotency key -> offline queue never double-submits.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    source_channel: Mapped[str] = mapped_column(String(20), default="WEB")  # WEB / OFFLINE_SYNC / SIMULATION
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    last_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category: Mapped[Category] = relationship()
    jurisdiction: Mapped[Jurisdiction | None] = relationship()
    evidence: Mapped[list["ComplaintEvidence"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    history: Mapped[list["ComplaintStatusHistory"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan",
        order_by="ComplaintStatusHistory.created_at",
    )

    __table_args__ = (
        Index("ix_complaints_geo", "latitude", "longitude"),
        Index("ix_complaints_queue", "status", "risk_score", "priority_score"),
        Index("ix_complaints_jur_status", "jurisdiction_id", "status"),
    )


class ComplaintStatusHistory(Base):
    """Immutable timeline event. Never updated, never deleted."""

    __tablename__ = "complaint_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), default="STATUS_CHANGE")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(80), default="SYSTEM")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    complaint: Mapped[Complaint] = relationship(back_populates="history")


class ComplaintEvidence(Base):
    __tablename__ = "complaint_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(20), default="REPORT")  # REPORT / FIELD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    complaint: Mapped[Complaint] = relationship(back_populates="evidence")


class ComplaintFollowup(Base):
    __tablename__ = "complaint_followups"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(24), default="FOLLOWUP")  # FOLLOWUP / FOLLOW / REOPEN_REQUEST / CONFIRM
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    field_worker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="ASSIGNED", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


# --------------------------------------------------------------------------
# Duplicates
# --------------------------------------------------------------------------
class DuplicateCluster(Base):
    __tablename__ = "duplicate_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_complaint_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lng: Mapped[float] = mapped_column(Float)
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DuplicateCandidate(Base):
    """Audit trail of what the duplicate engine proposed and what the human did."""

    __tablename__ = "duplicate_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    candidate_complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    similarity: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float] = mapped_column(Float)
    text_similarity: Mapped[float] = mapped_column(Float)
    hours_apart: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(24), default="PENDING")  # PENDING/FOLLOWED/SEPARATE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Scores (kept with full explanation payloads)
# --------------------------------------------------------------------------
class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(12))
    factors: Mapped[list] = mapped_column(JSON)
    recommended_action: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(24), default="rule-v1")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class PriorityScore(Base):
    __tablename__ = "priority_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(12))
    factors: Mapped[list] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(24), default="rule-v1")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Ops
# --------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40), index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default="INFO")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class OfflineSyncQueue(Base):
    """Server-side record of actions that arrived from an offline device."""

    __tablename__ = "offline_sync_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    action_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="APPLIED", index=True)
    result_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SimulationRun(Base):
    """Bookkeeping for the Dasara surge simulation."""

    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    requested_count: Mapped[int] = mapped_column(Integer)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    queued: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_detected: Mapped[int] = mapped_column(Integer, default=0)
    high_priority: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(20), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
