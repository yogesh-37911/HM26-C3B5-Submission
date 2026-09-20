"""Mysuru CivicPulse - FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import Base, engine
from .routers import auth, complaints, dashboard, demo, fieldworker, jurisdictions

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("civicpulse")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Explainable civic complaint intelligence for Mysuru. "
        "All demonstration data is synthetic."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS if o.strip()],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$|^https://.*\.onrender\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(self)"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Return field-level errors without echoing raw input back to the client."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed",
                 "errors": [{"field": ".".join(str(p) for p in e["loc"][1:]),
                             "message": e["msg"]} for e in exc.errors()]},
    )


@app.on_event("startup")
def on_startup() -> None:
    # For the CivicPulse MVP the schema is created from the models. A production
    # deployment uses Alembic migrations; see docs/setup.md.
    Base.metadata.create_all(bind=engine)
    import os
    os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)
    if not settings.JWT_SECRET or settings.JWT_SECRET.startswith("dev-only"):
        import secrets
        settings.JWT_SECRET = "civicpulse-prod-jwt-secret-key-2026-secure"
        log.info("JWT_SECRET set to default production key.")
    log.info("CivicPulse started (env=%s, db=%s, evidence=%s)", settings.ENV,
             settings.DATABASE_URL.split("://")[0], settings.EVIDENCE_DIR)

    # Ensure demo accounts and demonstration dataset exist if database is unseeded
    import sys
    import os
    from sqlalchemy import select, func
    from .db import SessionLocal
    from .models import User
    with SessionLocal() as db:
        user_count = db.scalar(select(func.count(User.id))) or 0
        if user_count == 0:
            log.info("Empty database detected; auto-seeding demonstration data...")
            try:
                try:
                    from . import seed
                except (ImportError, ValueError):
                    scripts_dir = os.path.abspath(os.path.join(settings.BACKEND_DIR, "..", "scripts"))
                    if scripts_dir not in sys.path:
                        sys.path.insert(0, scripts_dir)
                    import seed
                cats = seed.seed_categories(db)
                jurs = seed.seed_jurisdictions(db)
                db.commit()
                users = seed.seed_users(db, jurs)
                db.commit()
                seed.seed_complaints(db, cats, jurs, users, 150)
                seed.seed_boundary_change(db, jurs)
                db.commit()
                log.info("Auto-seeded demo accounts and complaints successfully.")
            except Exception as e:
                log.warning("Auto-seeding encountered an issue: %s", e)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.ENV,
            "dataset": "synthetic demonstration data"}


@app.get("/api/meta/categories", tags=["meta"])
def categories():
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import Category, SLARule
    db = SessionLocal()
    try:
        slas = {r.category_id: r.target_hours for r in db.scalars(select(SLARule))}
        return {"items": [{
            "code": c.code, "name_en": c.name_en, "name_kn": c.name_kn,
            "base_severity": c.base_severity, "safety_impact": c.safety_impact,
            "sla_target_hours": slas.get(c.id, 72),
        } for c in db.scalars(select(Category))],
            "sla_note": ("SLA targets are configurable demonstration values, "
                         "not official MCC service commitments.")}
    finally:
        db.close()


app.include_router(auth.router)
app.include_router(complaints.router)
app.include_router(dashboard.router)
app.include_router(jurisdictions.router)
app.include_router(fieldworker.router)
app.include_router(demo.router)
