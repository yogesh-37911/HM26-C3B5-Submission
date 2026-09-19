"""Pydantic request/response models.

Mass-assignment defence: request models list ONLY client-settable fields.
Priority, risk, verification, jurisdiction and status are server-computed and
are not accepted from the client under any circumstances.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


#: Deliberately a permissive pattern rather than pydantic's EmailStr, which
#: rejects special-use domains such as the `@demo.local` accounts the judges
#: log in with. Email syntax is not a security control; authentication is.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(max_length=160, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=4, max_length=128)

    @field_validator("email")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    language: str
    jurisdiction_id: int | None = None


class ComplaintCreate(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    description: str = Field(min_length=10, max_length=4000)
    category_code: str = Field(max_length=48)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    landmark: str | None = Field(default=None, max_length=180)
    language: str = Field(default="en", max_length=5)
    #: Client-generated UUID. Makes offline replay safe.
    idempotency_key: str | None = Field(default=None, max_length=64)
    client_created_at: datetime | None = None
    #: Set when the citizen chose "submit anyway" on a duplicate warning.
    acknowledged_duplicate_of: str | None = Field(default=None, max_length=24)

    @field_validator("title", "description", "landmark")
    @classmethod
    def strip_control(cls, v):
        if v is None:
            return v
        # Strip control characters. HTML is escaped at render time; we store
        # the raw user text rather than mangling it here.
        return "".join(ch for ch in v if ch == "\n" or ord(ch) >= 32).strip()


class DuplicateCheckRequest(BaseModel):
    title: str = ""
    description: str = ""
    category_code: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class StatusChangeRequest(BaseModel):
    to_status: str
    note: str | None = Field(default=None, max_length=1000)


class AssignRequest(BaseModel):
    field_worker_id: int
    note: str | None = Field(default=None, max_length=500)


class FollowupRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1000)
    kind: str = Field(default="FOLLOWUP", max_length=24)


class JurisdictionVersionCreate(BaseModel):
    jurisdiction_id: int
    version_label: str = Field(max_length=32)
    effective_from: datetime
    effective_to: datetime | None = None
    boundary: list[list[float]] = Field(min_length=3)
    close_previous: bool = True
    source_note: str | None = None


class SurgeRequest(BaseModel):
    count: int = Field(default=5000, ge=1, le=50000)
    label: str = Field(default="Dasara surge", max_length=80)
    batch_size: int = Field(default=250, ge=10, le=2000)


class OfflineAction(BaseModel):
    idempotency_key: str = Field(max_length=64)
    action_type: str = Field(max_length=40)
    payload: dict
    client_created_at: datetime | None = None


class OfflineSyncRequest(BaseModel):
    actions: list[OfflineAction] = Field(max_length=100)


TokenResponse.model_rebuild()
