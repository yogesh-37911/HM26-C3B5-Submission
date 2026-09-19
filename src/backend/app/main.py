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
    # For the hackathon MVP the schema is created from the models. A production
    # deployment uses Alembic migrations; see docs/setup.md.
    Base.metadata.create_all(bind=engine)
    if settings.JWT_SECRET.startswith("dev-only") and settings.ENV == "production":
        raise RuntimeError("JWT_SECRET must be set in production.")
    log.info("CivicPulse started (env=%s, db=%s)", settings.ENV,
             settings.DATABASE_URL.split("://")[0])


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
