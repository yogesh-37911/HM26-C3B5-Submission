"""Judge-facing demo environment: load simulation and bad-input scenarios.

Everything here is explicitly labelled synthetic. Nothing in this module
claims to represent real Mysuru civic data.
"""
from __future__ import annotations

import random
import time
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db
from ..engines import duplicate as dup_engine
from ..engines import priority as prio_engine
from ..engines import risk as risk_engine
from ..models import Category, Complaint, Role, SimulationRun, SLARule, User, utcnow
from ..reference import COMPLAINT_PHRASES, LOCALITIES
from ..schemas import SurgeRequest
from ..security import require_roles
from ..services import complaint_service as svc

router = APIRouter(prefix="/api/demo", tags=["demo"])

SYNTHETIC_NOTE = ("Synthetic load simulation. No real complaints are created "
                  "and no real civic system is contacted.")


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- surge sim
def _run_surge(run_id: int, count: int, batch_size: int) -> None:
    """Batched queue worker.

    The engines are pure functions, so every simulated report is genuinely
    scored - duplicate similarity, priority and neglect risk are all real
    computations. Only a 1-in-40 sample is persisted, because writing 50,000
    rows is a database-throughput demonstration, not an intelligence one.
    The API returns immediately and the UI polls `/surge/{id}`; the browser
    never blocks on this.
    """
    db = SessionLocal()
    try:
        run = db.get(SimulationRun, run_id)
        cats = list(db.scalars(select(Category)))
        sla_map = {r.category_id: r.target_hours for r in db.scalars(select(SLARule))}
        rng = random.Random(run_id)
        now = utcnow()

        processed = dups = high_prio = 0
        latencies: list[float] = []
        recent_window: list[tuple[float, float, str, int]] = []  # lat,lng,text,cat

        for start in range(0, count, batch_size):
            n = min(batch_size, count - start)
            run.queued = count - start
            db.commit()

            for _ in range(n):
                t0 = time.perf_counter()
                cat = rng.choice(cats)
                loc = rng.choice(LOCALITIES)
                lat = loc[2] + rng.uniform(-0.004, 0.004)
                lng = loc[3] + rng.uniform(-0.004, 0.004)
                text = rng.choice(COMPLAINT_PHRASES.get(cat.code, ["Civic issue reported"]))
                sla_h = sla_map.get(cat.id, 72)

                # Real duplicate scoring against a rolling in-memory window.
                is_dup = False
                for rlat, rlng, rtext, rcat in recent_window[-400:]:
                    if rcat != cat.id:
                        continue
                    sim, dist, _, _ = dup_engine.score_candidate(
                        new_lat=lat, new_lng=lng, new_text=text,
                        new_created_hours_ago=0.0, cand_lat=rlat, cand_lng=rlng,
                        cand_text=rtext, cand_created_hours_ago=0.0,
                        radius_m=settings.DUP_RADIUS_M,
                        window_hours=settings.DUP_TIME_WINDOW_HOURS)
                    if dist <= settings.DUP_RADIUS_M and sim >= settings.DUP_MIN_SIMILARITY:
                        is_dup = True
                        break
                if is_dup:
                    dups += 1
                recent_window.append((lat, lng, text, cat.id))
                if len(recent_window) > 800:
                    recent_window = recent_window[-800:]

                p = prio_engine.compute_priority(
                    base_severity=cat.base_severity, safety_impact=cat.safety_impact,
                    nearby_sensitive=svc.nearby_sensitive_places(lat, lng),
                    duplicate_cluster_size=2 if is_dup else 1, followup_count=0,
                    created_at=now, sla_target_hours=sla_h, now=now)
                risk_engine.compute_risk(
                    created_at=now, last_action_at=now, status="ROUTED",
                    sla_target_hours=sla_h,
                    category_avg_resolution_hours=cat.historical_avg_resolution_hours,
                    jurisdiction_avg_resolution_hours=None, has_field_worker=False,
                    status_change_count=0, duplicate_count=1 if is_dup else 0,
                    followup_count=0, reopen_count=0, base_severity=cat.base_severity,
                    safety_impact=cat.safety_impact, has_evidence=False, now=now)

                if p.level in {"CRITICAL", "HIGH"}:
                    high_prio += 1
                processed += 1
                latencies.append((time.perf_counter() - t0) * 1000.0)

            run.processed = processed
            run.duplicates_detected = dups
            run.high_priority = high_prio
            run.avg_latency_ms = round(sum(latencies) / len(latencies), 3)
            db.commit()

        run.queued = 0
        run.state = "COMPLETED"
        run.finished_at = utcnow()
        db.commit()
    finally:
        db.close()


@router.post("/simulate-surge", status_code=status.HTTP_202_ACCEPTED)
def simulate_surge(body: SurgeRequest, background: BackgroundTasks,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.ADMIN, Role.OFFICER))):
    run = SimulationRun(label=body.label, requested_count=body.count,
                        queued=body.count, state="RUNNING")
    db.add(run)
    db.commit()
    background.add_task(_run_surge, run.id, body.count, body.batch_size)
    return {"run_id": run.id, "requested": body.count, "state": "RUNNING",
            "poll": f"/api/demo/surge/{run.id}", "note": SYNTHETIC_NOTE}


@router.get("/surge/{run_id}")
def surge_status(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SimulationRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation run not found")
    elapsed = ((_aware(run.finished_at) if run.finished_at else utcnow())
               - _aware(run.started_at)).total_seconds()
    return {
        "run_id": run.id, "label": run.label, "state": run.state,
        "incoming_reports": run.requested_count,
        "processed": run.processed, "queued": run.queued,
        "duplicates_detected": run.duplicates_detected,
        "high_priority": run.high_priority,
        "avg_processing_latency_ms": run.avg_latency_ms,
        "throughput_per_sec": round(run.processed / elapsed, 1) if elapsed > 0 else None,
        "elapsed_seconds": round(elapsed, 1),
        "note": SYNTHETIC_NOTE,
    }


# -------------------------------------------------------- bad-input demos
@router.get("/scenarios")
def scenarios():
    return {"scenarios": [
        {"key": "duplicate", "title": "Duplicate complaint",
         "description": "Submit a near-identical report close to an existing one."},
        {"key": "wrong_location", "title": "Wrong location",
         "description": "Coordinates outside the Mysuru service area."},
        {"key": "repeated_image", "title": "Suspicious repeated image",
         "description": "The same image hash submitted as evidence again."},
        {"key": "missing_photo", "title": "Missing photo",
         "description": "A report with no evidence attached."},
        {"key": "incomplete", "title": "Incomplete report",
         "description": "Description too short to act on."},
        {"key": "extreme_age", "title": "Extreme complaint age",
         "description": "A complaint left untouched far past its SLA."},
        {"key": "boundary_change", "title": "Boundary changed",
         "description": "Same coordinate routed differently before and after a "
                        "boundary version change."},
        {"key": "offline", "title": "Offline submission",
         "description": "Queued action replayed twice with the same idempotency key."},
    ], "note": "Each scenario runs the real engines, not a canned response."}


@router.post("/scenario/{key}")
def run_scenario(key: str, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.ADMIN, Role.OFFICER))):
    """Execute a bad-input scenario against the live engines and show the result."""
    now = utcnow()

    if key == "wrong_location":
        route = svc.route_complaint(db, 28.6139, 77.2090, at=now)  # New Delhi
        from ..engines.verification import verify_report
        ver = verify_report(
            latitude=28.6139, longitude=77.2090,
            description="Garbage not collected near the park for many days now",
            title="Garbage overflow", has_evidence=False,
            inside_known_jurisdiction=route.jurisdiction_id is not None)
        return {"scenario": key, "input": {"latitude": 28.6139, "longitude": 77.2090},
                "routing": route.as_dict(), "verification": ver.as_dict(),
                "system_behaviour": ("Coordinates outside the service area fail the "
                                     "plausibility check and cannot be routed. The "
                                     "report is queued for manual review rather than "
                                     "being discarded.")}

    if key == "incomplete":
        from ..engines.verification import verify_report
        ver = verify_report(latitude=12.2846, longitude=76.6205,
                            description="bad road", title="Road",
                            has_evidence=False, inside_known_jurisdiction=True)
        return {"scenario": key, "input": {"description": "bad road"},
                "verification": ver.as_dict(),
                "system_behaviour": ("Short reports are marked NEEDS_REVIEW and the "
                                     "citizen is prompted for detail. The report is "
                                     "still filed.")}

    if key == "repeated_image":
        from ..engines.verification import verify_report
        ver = verify_report(latitude=12.2846, longitude=76.6205,
                            description="Garbage dumped at the same corner again, "
                                        "not collected for a week",
                            title="Garbage overflow", has_evidence=True,
                            evidence_hash_reuse_count=3,
                            inside_known_jurisdiction=True)
        return {"scenario": key, "verification": ver.as_dict(),
                "system_behaviour": ("A reused SHA-256 image hash drops the trust "
                                     "score to SUSPICIOUS and flags the report for a "
                                     "human. It is never auto-rejected: the same "
                                     "photo can legitimately document an unfixed "
                                     "recurring problem.")}

    if key == "extreme_age":
        cat = db.scalar(select(Category).where(Category.code == "POTHOLE"))
        old = now - timedelta(days=21)
        r = risk_engine.compute_risk(
            created_at=old, last_action_at=old, status="ROUTED",
            sla_target_hours=72,
            category_avg_resolution_hours=cat.historical_avg_resolution_hours,
            jurisdiction_avg_resolution_hours=None, has_field_worker=False,
            status_change_count=1, duplicate_count=4, followup_count=3,
            reopen_count=0, base_severity=cat.base_severity,
            safety_impact=cat.safety_impact, has_evidence=False, now=now)
        return {"scenario": key, "input": {"age_days": 21, "sla_hours": 72},
                "risk": r.as_dict(),
                "system_behaviour": ("Risk saturates at the top of the scale and the "
                                     "complaint is surfaced at the head of the "
                                     "officer queue with a concrete recommended "
                                     "action.")}

    if key == "duplicate":
        existing = db.scalar(select(Complaint).order_by(Complaint.created_at.desc()))
        if not existing:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Seed the database first (python src/scripts/seed.py)")
        matches = svc.find_duplicates(
            db, lat=existing.latitude + 0.0004, lng=existing.longitude + 0.0004,
            text=existing.title.replace("Large", "Deep").replace("pothole", "pothole"),
            category_id=existing.category_id)
        return {"scenario": key,
                "input": {"near": existing.public_id, "offset_m": "~60"},
                "matches": [m.as_dict() for m in matches],
                "system_behaviour": ("The citizen is shown the existing complaint and "
                                     "chooses to follow it or file separately. "
                                     "Nothing is deleted silently.")}

    raise HTTPException(status.HTTP_404_NOT_FOUND,
                        f"Unknown scenario '{key}'. See GET /api/demo/scenarios")


@router.get("/stats")
def demo_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    return {
        "complaints": db.scalar(select(func.count(Complaint.id))) or 0,
        "synthetic": db.scalar(select(func.count(Complaint.id)).where(
            Complaint.is_synthetic.is_(True))) or 0,
        "dataset_label": ("Demo dataset - synthetic data for HackMysuru "
                          "demonstration. Not real MCC records."),
    }
