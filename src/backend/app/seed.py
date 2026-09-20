#!/usr/bin/env python3
"""Seed the CivicPulse database with synthetic demonstration data.

    python src/scripts/seed.py [--complaints 500] [--reset]

EVERYTHING generated here is synthetic. Ward boundaries are generated
polygons, not authoritative MCC GIS data. Statistics produced from this
dataset do not describe real Mysuru.

The generator is seeded with a fixed RNG seed so the demo is reproducible:
the same complaint IDs, risk scores and duplicate clusters appear on every
machine, which matters when you are demoing from a script.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engines.geo import polygon_bbox  # noqa: E402
from app.models import (  # noqa: E402
    Assignment,
    Category,
    Complaint,
    ComplaintEvidence,
    ComplaintFollowup,
    ComplaintStatus,
    DuplicateCluster,
    Jurisdiction,
    JurisdictionVersion,
    Role,
    SLARule,
    User,
)
from app.reference import CATEGORIES, COMPLAINT_PHRASES, LOCALITIES  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import complaint_service as svc  # noqa: E402

RNG = random.Random(20260918)
NOW = datetime.now(timezone.utc)

DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "CivicPulse@2026")

MCC_WARD_COUNT = 65
CITY_CENTRE = (12.3052, 76.6552)


# ------------------------------------------------------------------ helpers
def hex_polygon(lat: float, lng: float, radius_m: float, sides: int = 7) -> list[list[float]]:
    """Generate a slightly irregular polygon around a centre point."""
    ring = []
    for i in range(sides):
        angle = 2 * math.pi * i / sides
        r = radius_m * RNG.uniform(0.82, 1.18)
        dlat = (r * math.cos(angle)) / 111_320.0
        dlng = (r * math.sin(angle)) / (111_320.0 * math.cos(math.radians(lat)))
        ring.append([round(lat + dlat, 6), round(lng + dlng, 6)])
    return ring


#: Ward radius in metres. Wards are deliberately generated around the demo
#: locality list rather than on an abstract spiral, so that ward coverage and
#: the places complaints actually get reported from are the same geography.
WARD_RADIUS_M = 520.0


def ward_centre(i: int) -> tuple[float, float, str]:
    """Return (lat, lng, locality_name) for ward index i (0-based).

    Wards are distributed round-robin across the demo localities; wards sharing
    a locality are offset onto a small ring so their boundaries sit side by side
    instead of on top of each other.
    """
    loc = LOCALITIES[i % len(LOCALITIES)]
    tier = i // len(LOCALITIES)          # 0, 1, 2 for 65 wards over 25 localities
    if tier == 0:
        return loc[2], loc[3], loc[0]
    angle = (i * 2.399963) % (2 * math.pi)
    dist = WARD_RADIUS_M * (1.55 * tier)
    dlat = (dist * math.cos(angle)) / 111_320.0
    dlng = (dist * math.sin(angle)) / (111_320.0 * math.cos(math.radians(loc[2])))
    return loc[2] + dlat, loc[3] + dlng, loc[0]


def add_version(db, jur, label, boundary, eff_from, eff_to=None, note=None):
    min_lat, max_lat, min_lng, max_lng = polygon_bbox(boundary)
    v = JurisdictionVersion(
        jurisdiction_id=jur.id, version_label=label, effective_from=eff_from,
        effective_to=eff_to, boundary_json=boundary, min_lat=min_lat, max_lat=max_lat,
        min_lng=min_lng, max_lng=max_lng,
        source_note=note or "Synthetic demonstration boundary - not authoritative GIS data.")
    db.add(v)
    return v


# ------------------------------------------------------------------- stages
def seed_categories(db) -> list[Category]:
    cats = []
    for code, en, kn, sev, safety, sla_h, hist in CATEGORIES:
        c = Category(code=code, name_en=en, name_kn=kn, base_severity=sev,
                     safety_impact=safety, historical_avg_resolution_hours=hist)
        db.add(c)
        db.flush()
        db.add(SLARule(category_id=c.id, target_hours=sla_h, is_demo_value=True))
        cats.append(c)
    print(f"  categories: {len(cats)} (+ demo SLA rules)")
    return cats


def seed_jurisdictions(db) -> list[Jurisdiction]:
    jurs = []
    base_from = NOW - timedelta(days=365)

    # 65 MCC wards.
    for i in range(MCC_WARD_COUNT):
        lat, lng, locality = ward_centre(i)
        j = Jurisdiction(authority="Mysuru City Corporation", authority_type="MUNICIPAL",
                         ward_number=i + 1, name=f"MCC Ward {i + 1} ({locality})",
                         contact_email=f"ward{i + 1}@mcc.demo.local")
        db.add(j)
        db.flush()
        add_version(db, j, "2026-01", hex_polygon(lat, lng, WARD_RADIUS_M),
                    base_from, None)
        jurs.append(j)

    # Adjacent panchayats / town bodies on the periphery.
    peripheral = [("Yelwal Town Panchayat", 12.3860, 76.5750),
                  ("Rammanahalli Gram Panchayat", 12.3612, 76.5885),
                  ("Kadakola Gram Panchayat", 12.2180, 76.6480),
                  ("Hootagalli City Municipal Council", 12.3520, 76.5960),
                  ("Bogadi Gram Panchayat", 12.3212, 76.5942)]
    for name, lat, lng in peripheral:
        atype = "PANCHAYAT" if "Panchayat" in name else "MUNICIPAL"
        j = Jurisdiction(authority=name, authority_type=atype, ward_number=None,
                         name=name, contact_email="office@panchayat.demo.local")
        db.add(j)
        db.flush()
        add_version(db, j, "2026-01", hex_polygon(lat, lng, 900), base_from, None)
        jurs.append(j)

    print(f"  jurisdictions: {len(jurs)} ({MCC_WARD_COUNT} MCC wards + "
          f"{len(peripheral)} peripheral bodies), 1 boundary version each")
    return jurs


def seed_users(db, jurs) -> dict:
    users: dict[str, list[User]] = {"citizen": [], "officer": [], "worker": [], "admin": []}
    pw = hash_password(DEMO_PASSWORD)

    demo_accounts = [
        ("citizen@demo.local", "Demo Citizen", Role.CITIZEN, None),
        ("officer@demo.local", "Demo Officer", Role.OFFICER, None),   # City-wide Nodal Officer
        ("worker@demo.local", "Demo Field Worker", Role.FIELD_WORKER, jurs[41].id),
        ("admin@demo.local", "Demo Admin", Role.ADMIN, None),
    ]
    for email, name, role, jid in demo_accounts:
        u = User(email=email, password_hash=pw, full_name=name, role=role.value,
                 jurisdiction_id=jid, language="en")
        db.add(u)
        db.flush()
        users[{"CITIZEN": "citizen", "OFFICER": "officer",
               "FIELD_WORKER": "worker", "ADMIN": "admin"}[role.value]].append(u)

    first_names = ["Anil", "Bhavana", "Chetan", "Deepa", "Girish", "Harsha", "Indira",
                   "Kavya", "Lohith", "Manjula", "Nagesh", "Pavithra", "Rakesh",
                   "Shruthi", "Umesh", "Vinay", "Yamuna", "Zoya"]
    last_names = ["Gowda", "Rao", "Shetty", "Prasad", "Murthy", "Kumar", "Hegde",
                  "Nayak", "Reddy", "Patil"]

    for i in range(60):
        u = User(email=f"citizen{i + 1}@demo.local", password_hash=pw,
                 full_name=f"{RNG.choice(first_names)} {RNG.choice(last_names)}",
                 role=Role.CITIZEN.value,
                 language=RNG.choice(["en", "en", "kn"]),
                 device_fingerprint=f"dev-{RNG.randrange(10**8):08d}")
        db.add(u)
        users["citizen"].append(u)

    for i in range(12):
        j = jurs[RNG.randrange(MCC_WARD_COUNT)]
        db.add(User(email=f"officer{i + 1}@demo.local", password_hash=pw,
                    full_name=f"{RNG.choice(first_names)} {RNG.choice(last_names)}",
                    role=Role.OFFICER.value, jurisdiction_id=j.id))
    for i in range(25):
        j = jurs[RNG.randrange(MCC_WARD_COUNT)]
        u = User(email=f"worker{i + 1}@demo.local", password_hash=pw,
                 full_name=f"{RNG.choice(first_names)} {RNG.choice(last_names)}",
                 role=Role.FIELD_WORKER.value, jurisdiction_id=j.id)
        db.add(u)
        users["worker"].append(u)

    db.flush()
    print(f"  users: 4 demo accounts + {len(users['citizen']) - 1} citizens, "
          f"12 officers, {len(users['worker']) - 1} field workers")
    return users


def seed_complaints(db, cats, jurs, users, n: int) -> None:
    citizens = users["citizen"]
    workers = list(db.scalars(
        __import__("sqlalchemy").select(User).where(User.role == Role.FIELD_WORKER.value)))
    sla_map = {r.category_id: r.target_hours
               for r in db.scalars(__import__("sqlalchemy").select(SLARule))}

    # Weight categories so the dataset looks like a real civic inbox:
    # garbage and potholes dominate, tree falls are rare.
    weights = {"GARBAGE": 22, "POTHOLE": 18, "STREETLIGHT": 14, "DRAIN": 11,
               "WATER": 9, "ILLEGAL_DUMPING": 7, "SEWAGE": 5, "STRAY_ANIMAL": 5,
               "FOOTPATH": 4, "SIGNAGE": 3, "PUBLIC_TOILET": 1, "TREE_FALL": 1}
    cat_pool = []
    for c in cats:
        cat_pool.extend([c] * weights.get(c.code, 3))

    created = 0
    # Per-category anchors so generated duplicates actually land in the same
    # category as the complaint they duplicate. Without this the duplicate
    # engine's category gate rejects almost every synthetic "duplicate".
    anchors: dict[int, list[tuple[float, float, str]]] = {}

    # Complaints are generated inside real ward footprints. A handful of wards
    # are deliberately over-weighted so the public dashboard has visibly
    # struggling areas to explain rather than a flat uniform distribution.
    ward_ids = list(range(MCC_WARD_COUNT))
    hot_wards = RNG.sample(ward_ids, 6)
    ward_pool = ward_ids + hot_wards * 7

    for i in range(n):
        cat = RNG.choice(cat_pool)

        pool = anchors.get(cat.id, [])
        if pool and RNG.random() < 0.20:
            # Genuine duplicate: several neighbours reporting the same pothole.
            a_lat, a_lng, a_loc = RNG.choice(pool)
            lat = a_lat + RNG.uniform(-0.0006, 0.0006)   # within ~70m
            lng = a_lng + RNG.uniform(-0.0006, 0.0006)
            loc = next((L for L in LOCALITIES if L[0] == a_loc), LOCALITIES[0])
        else:
            w_lat, w_lng, w_loc = ward_centre(RNG.choice(ward_pool))
            # Keep the point comfortably inside the ~520m ward polygon.
            r = WARD_RADIUS_M * 0.62 * math.sqrt(RNG.random())
            theta = RNG.uniform(0, 2 * math.pi)
            lat = w_lat + (r * math.cos(theta)) / 111_320.0
            lng = w_lng + (r * math.sin(theta)) / (111_320.0 * math.cos(math.radians(w_lat)))
            loc = next((L for L in LOCALITIES if L[0] == w_loc), LOCALITIES[0])
            anchors.setdefault(cat.id, []).append((lat, lng, loc[0]))
            if len(anchors[cat.id]) > 40:
                anchors[cat.id].pop(0)

        # Age distribution: mostly recent, with a long tail of neglected cases.
        r = RNG.random()
        if r < 0.45:
            age_h = RNG.uniform(0.5, 48)
        elif r < 0.80:
            age_h = RNG.uniform(48, 240)
        else:
            age_h = RNG.uniform(240, 1400)   # the stale tail the product exists for
        created_at = NOW - timedelta(hours=age_h)

        phrase = RNG.choice(COMPLAINT_PHRASES.get(cat.code, ["Civic issue reported"]))
        title = f"{cat.name_en} near {loc[0]}"
        description = f"{phrase} near {loc[0]}, Mysuru."

        citizen = RNG.choice(citizens)
        sla_h = sla_map.get(cat.id, 72)

        c = Complaint(
            public_id=f"CIV-2026-{created + 1:06d}",
            citizen_id=citizen.id, category_id=cat.id, title=title,
            description=description, landmark=loc[0], latitude=lat, longitude=lng,
            created_at=created_at, last_action_at=created_at,
            sla_target_hours=sla_h, sla_due_at=created_at + timedelta(hours=sla_h),
            is_synthetic=True, source_channel="SIMULATION",
        )
        db.add(c)
        db.flush()

        # --- route (against the boundary version active when it was filed) ---
        route = svc.route_complaint(db, lat, lng, at=created_at)
        c.jurisdiction_id = route.jurisdiction_id
        c.jurisdiction_version_id = route.jurisdiction_version_id
        c.routing_confidence = route.confidence
        c.routing_reason = route.reason
        svc.add_event(db, c, event_type="SUBMITTED", to_status="SUBMITTED",
                      note="Complaint submitted by citizen.", at=created_at)
        svc.add_event(db, c, event_type="ROUTED", from_status="SUBMITTED",
                      to_status="ROUTED", payload=route.as_dict(), at=created_at,
                      note=(f"Routed to {route.authority}"
                            + (f" Ward {route.ward_number}" if route.ward_number else "")
                            + f" (boundary version {route.version_label})."))
        c.status = ComplaintStatus.ROUTED.value
        c.status_change_count = 1

        # --- evidence (65% of reports carry a photo) ---
        if RNG.random() < 0.65:
            # A small pool of reused hashes seeds the "repeated evidence" signal.
            digest = (f"{RNG.randrange(16**64):064x}" if RNG.random() > 0.05
                      else "a" * 64)
            db.add(ComplaintEvidence(
                complaint_id=c.id, filename=f"report_{c.public_id}.jpg",
                mime_type="image/jpeg", size_bytes=RNG.randrange(180_000, 3_800_000),
                sha256=digest, uploaded_by_id=citizen.id, stage="REPORT",
                created_at=created_at))

        # --- lifecycle progression, biased by age ---
        progress = RNG.random()
        cursor = created_at
        assigned = False

        if age_h > 6 and progress < 0.78:
            cursor += timedelta(hours=RNG.uniform(1, min(age_h * 0.4, 40)))
            worker = RNG.choice(workers)
            db.add(Assignment(complaint_id=c.id, field_worker_id=worker.id,
                              assigned_at=cursor, is_active=True))
            c.status = ComplaintStatus.ASSIGNED.value
            c.status_change_count += 1
            c.last_action_at = cursor
            assigned = True
            svc.add_event(db, c, event_type="ASSIGNED", from_status="ROUTED",
                          to_status="ASSIGNED", actor_label="officer@demo.local",
                          note=f"Assigned to field worker {worker.full_name}.", at=cursor)

        if assigned and progress < 0.62 and cursor < NOW:
            cursor += timedelta(hours=RNG.uniform(1, 30))
            if cursor < NOW:
                c.status = ComplaintStatus.IN_PROGRESS.value
                c.status_change_count += 1
                c.last_action_at = cursor
                svc.add_event(db, c, event_type="FIELD_STARTED", from_status="ASSIGNED",
                              to_status="IN_PROGRESS", actor_label="worker@demo.local",
                              note="Field worker started inspection.", at=cursor)

        if c.status == ComplaintStatus.IN_PROGRESS.value and progress < 0.46:
            cursor += timedelta(hours=RNG.uniform(1, 36))
            if cursor < NOW:
                c.status = ComplaintStatus.RESOLVED.value
                c.status_change_count += 2
                c.last_action_at = cursor
                c.resolved_at = cursor
                svc.add_event(db, c, event_type="FIELD_VERIFIED",
                              from_status="IN_PROGRESS", to_status="FIELD_VERIFIED",
                              actor_label="worker@demo.local",
                              note="Work completed and verified on site.", at=cursor)
                svc.add_event(db, c, event_type="STATUS_CHANGE",
                              from_status="FIELD_VERIFIED", to_status="RESOLVED",
                              actor_label="officer@demo.local",
                              note="Officer closed the complaint as resolved.", at=cursor)
                db.add(ComplaintEvidence(
                    complaint_id=c.id, filename=f"resolution_{c.public_id}.jpg",
                    mime_type="image/jpeg", size_bytes=RNG.randrange(200_000, 2_000_000),
                    sha256=f"{RNG.randrange(16**64):064x}", stage="FIELD",
                    created_at=cursor))
                # A few resolutions do not stick.
                if RNG.random() < 0.07:
                    reopen_at = cursor + timedelta(hours=RNG.uniform(12, 96))
                    if reopen_at < NOW:
                        c.status = ComplaintStatus.REOPENED.value
                        c.reopen_count = 1
                        c.status_change_count += 1
                        c.resolved_at = None
                        c.last_action_at = reopen_at
                        db.add(ComplaintFollowup(
                            complaint_id=c.id, user_id=citizen.id,
                            message="The issue has come back, it was not fixed properly.",
                            kind="REOPEN_REQUEST", created_at=reopen_at))
                        svc.add_event(db, c, event_type="REOPENED",
                                      from_status="RESOLVED", to_status="REOPENED",
                                      actor_label=citizen.email,
                                      note="Citizen reports the issue is not resolved.",
                                      at=reopen_at)
        elif RNG.random() < 0.03:
            c.status = ComplaintStatus.REJECTED.value
            c.status_change_count += 1
            svc.add_event(db, c, event_type="STATUS_CHANGE", to_status="REJECTED",
                          actor_label="officer@demo.local",
                          note="Rejected: outside municipal scope, forwarded to the "
                               "relevant department.", at=cursor)

        # --- follow-ups: older open complaints attract more chasing ---
        if c.status not in {"RESOLVED", "REJECTED"} and age_h > 48:
            for _ in range(RNG.choice([0, 0, 1, 1, 2, 3])):
                fu_at = created_at + timedelta(hours=RNG.uniform(24, max(age_h, 25)))
                if fu_at < NOW:
                    db.add(ComplaintFollowup(
                        complaint_id=c.id, user_id=citizen.id,
                        message="Still not resolved, please look into this.",
                        kind="FOLLOWUP", created_at=fu_at))
                    c.followup_count += 1

        created += 1
        if created % 100 == 0:
            db.commit()
            print(f"    ... {created}/{n} complaints")

    db.commit()

    # --- duplicate clustering pass over the finished dataset ---
    print("  clustering duplicates ...")
    all_c = list(db.scalars(__import__("sqlalchemy").select(Complaint)))
    clustered = 0
    for c in all_c:
        if c.duplicate_cluster_id:
            continue
        matches = svc.find_duplicates(
            db, lat=c.latitude, lng=c.longitude,
            text=f"{c.title} {c.description}", category_id=c.category_id,
            created_at=c.created_at, exclude_id=c.id)
        if not matches:
            continue
        top = db.get(Complaint, matches[0].complaint_id)
        if top.duplicate_cluster_id:
            cluster = db.get(DuplicateCluster, top.duplicate_cluster_id)
        else:
            cluster = DuplicateCluster(primary_complaint_id=top.id,
                                       category_id=top.category_id,
                                       centroid_lat=top.latitude,
                                       centroid_lng=top.longitude, member_count=1)
            db.add(cluster)
            db.flush()
            top.duplicate_cluster_id = cluster.id
        c.duplicate_cluster_id = cluster.id
        cluster.member_count += 1
        clustered += 1
    db.commit()
    print(f"  duplicate members linked: {clustered}")

    # --- verification + scoring pass ---
    print("  computing verification, priority and neglect risk ...")
    for idx, c in enumerate(all_c, 1):
        dup_n = max(svc.duplicate_cluster_size(db, c) - 1, 0)
        svc.run_verification(db, c, dup_count=dup_n,
                             routed=c.jurisdiction_id is not None)
        svc.recompute_scores(db, c)
        if idx % 200 == 0:
            db.commit()
    db.commit()
    print(f"  scored: {len(all_c)} complaints")


def seed_boundary_change(db, jurs) -> None:
    """Stage the boundary-change demo.

    Ward 42's 2026-10 version shrinks; the adjacent Bogadi Gram Panchayat
    expands to cover the released area. Complaints already filed keep their
    2026-01 routing.
    """
    ward42 = next(j for j in jurs if j.ward_number == 42)
    lat, lng, _loc = ward_centre(41)
    future = NOW + timedelta(days=13)   # inside the demo window, easy to trigger
    add_version(db, ward42, "2026-10", hex_polygon(lat, lng, 380), future, None,
                note="Demonstration boundary revision: Ward 42 reduced in extent.")
    db.commit()
    print(f"  staged boundary revision: MCC Ward 42 version 2026-10 effective "
          f"{future.date().isoformat()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--complaints", type=int, default=500)
    ap.add_argument("--reset", action="store_true",
                    help="Drop and recreate all tables before seeding.")
    args = ap.parse_args()

    if args.reset:
        print("Dropping existing tables ...")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(Complaint).count()
        if existing and not args.reset:
            print(f"Database already holds {existing} complaints. "
                  "Re-run with --reset to rebuild.")
            return

        print("Seeding synthetic demonstration data for Mysuru CivicPulse ...")
        cats = seed_categories(db)
        jurs = seed_jurisdictions(db)
        db.commit()
        users = seed_users(db, jurs)
        db.commit()
        seed_complaints(db, cats, jurs, users, args.complaints)
        seed_boundary_change(db, jurs)

        total = db.query(Complaint).count()
        print("\nDone.")
        print(f"  complaints: {total}")
        print(f"  demo login password: {DEMO_PASSWORD}")
        print("  accounts: citizen@demo.local / officer@demo.local / "
              "worker@demo.local / admin@demo.local")
        print("\n  Demo dataset - synthetic data for Mysuru CivicPulse demonstration.")
        print("  These records do not represent real Mysuru civic data.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
