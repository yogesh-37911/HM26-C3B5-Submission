"""Password hashing, JWT issue/verify, and role-based access control."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Role, User

bearer = HTTPBearer(auto_error=False)

#: bcrypt hashes at most 72 bytes of input and raises on anything longer.
#: We truncate explicitly rather than let a long passphrase 500 the endpoint.
BCRYPT_MAX_BYTES = 72


def _prepare(raw: str) -> bytes:
    return raw.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_prepare(raw), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(raw), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "jur": user.jurisdiction_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def get_current_user(
    token_param: str | None = Query(None, alias="token"),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    raw_token = creds.credentials if creds else token_param
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    payload = decode_token(raw_token)
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def get_optional_user(
    token_param: str | None = Query(None, alias="token"),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    raw_token = creds.credentials if creds else token_param
    if not raw_token:
        return None
    try:
        payload = decode_token(raw_token)
    except HTTPException:
        return None
    return db.get(User, int(payload["sub"]))


def require_roles(*roles: Role):
    """Dependency factory enforcing role membership.

    A citizen hitting an officer endpoint gets 403, not a filtered result set.
    """
    allowed = {r.value for r in roles}

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role {user.role} is not permitted to perform this action.",
            )
        return user

    return _dep


def assert_jurisdiction_access(user: User, jurisdiction_id: int | None) -> None:
    """Officers see only their own jurisdiction. Admins see everything.

    This is the IDOR guard: object-level authorisation, checked on the object
    actually loaded from the database, not on a client-supplied claim.
    """
    if user.role == Role.ADMIN.value:
        return
    if user.role == Role.OFFICER.value:
        if user.jurisdiction_id is None or jurisdiction_id is None:
            return  # city-wide officer or newly submitted unrouted complaint
        if jurisdiction_id != user.jurisdiction_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Complaint belongs to a jurisdiction outside your assignment.",
            )
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted.")

