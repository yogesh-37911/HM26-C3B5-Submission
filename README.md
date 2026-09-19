# Mysuru CivicPulse

**"From complaint to closure - before civic issues are forgotten."**

An explainable civic intelligence platform that routes, verifies,
prioritizes and tracks civic complaints for Mysuru - built for HackMysuru
1.0, Phase 1, addressing **Sub-problem 2: Follow-through**.

> Demo dataset - synthetic data for HackMysuru demonstration. Screenshots
> and statistics in this document do not represent real Mysuru civic
> records.

---

## 1. Problem Understanding

Citizens in Mysuru can already report civic problems. The gap isn't
reporting - it's what happens *after*. Complaints stagnate with no one
noticing, get duplicated across neighbours reporting the same pothole,
bounce between authorities as jurisdiction boundaries shift, and carry no
signal of which ones need attention *first*. A citizen has no way to know
whether their report disappeared into a queue or is actively being worked.

Our central differentiator: **a predictive civic complaint engine estimates
which open complaints are most likely to become neglected before they
become overdue**, and surfaces that to officers with a plain-language
explanation, not a black-box number.

## 2. Target Users & Mysuru Context

- **Citizens** - often on mobile, sometimes on weak/intermittent networks,
  in both English and Kannada, not all technically sophisticated.
- **Civic officers** - manage a ward-scoped queue of complaints across
  categories, need to know what's urgent and what's about to be forgotten.
- **Field workers** - do the on-ground work, often without reliable
  connectivity, need a mobile-first task list and evidence capture.
- **The public** - want visibility into whether their ward's civic
  problems are actually being resolved and why some areas lag.

Designed against real Mysuru constraints: 65 MCC wards, adjacent
town/gram panchayats, changing jurisdiction boundaries, and festival
(Dasara) traffic spikes that can push complaint volume 10x overnight.

## 3. Solution Overview

Three role-based interfaces (Citizen, Officer, Field Worker) plus a public
transparency dashboard, backed by five explainable intelligence engines:

| Engine | Answers |
|---|---|
| Neglect Risk | Which open complaints are about to go stale? |
| Priority | Which complaints should be fixed first? |
| Duplicate Detection | Is this the same issue someone already reported? |
| Verification | How much should we trust this report? |
| Jurisdiction Routing | Which authority handles this, under which boundary version? |

Every automated decision explains itself: WHAT happened, WHY, on WHAT DATA,
and WHAT a human can do about it. Nothing is ever silently deleted or
auto-rejected.

## 4. Architecture

```
src/
  backend/   FastAPI + SQLAlchemy, five pure-function intelligence engines
  frontend/  React + Vite + TypeScript, Leaflet maps, EN/KN toggle
  shared/    Cross-cutting type/contract references
  scripts/   seed.py - synthetic demo data generator
```

See **[docs/architecture.md](docs/architecture.md)** for component
diagrams, data flow, the complaint lifecycle state machine, database
schema, and security architecture (all as Mermaid diagrams).

## 5. Tech Stack & AI Usage

**Frontend:** React 18, Vite, TypeScript, Leaflet + OpenStreetMap (no paid
map API), Tailwind.
**Backend:** Python, FastAPI, SQLAlchemy 2.0, Pydantic, PyJWT, bcrypt.
**Database:** SQLite by default (zero setup); Postgres/Supabase supported
via `DATABASE_URL` with no code changes.
**Intelligence:** deterministic, explainable scoring engines - not opaque
ML. See "Decision Log" below for why. Full AI-tool disclosure is in
**[ai.md](ai.md)**.

## 6. Decision Log (Summary)

- **Explainable scoring over black-box ML.** The MVP has no real historical
  municipal outcome data to train or calibrate a model against, and an
  officer acting on a prioritisation needs to see why. Chose an additive,
  per-factor-attributed model with the same `score/level/factors/action`
  interface a trained classifier would expose later.
- **Versioned jurisdictions, not a hard-coded ward map.** Boundaries change;
  a `Jurisdiction` (stable identity) + `JurisdictionVersion` (dated
  geometry) split means a complaint's historical routing is immutable while
  new complaints use whatever boundary is currently active.
- **Report volume capped at 15/100 priority points.** A brigaded cosmetic
  complaint must never mathematically outrank a genuine hazard.
- **No PostGIS dependency.** Bounding-box SQL prefilter + Haversine in
  Python is accurate enough at city scale and keeps the zero-setup SQLite
  path viable; documented as a limitation for a scaled deployment.
- **Never auto-reject.** Verification's worst outcome is `SUSPICIOUS`,
  routed to a human - never silent deletion.
- Full log with alternatives considered: see
  `resource-templates/decision-log-template.md` for the format used.

## 7. Setup & Run

Full instructions: **[docs/setup.md](docs/setup.md)**.

Quick start:

```bash
# Backend
cd src/backend
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" sqlalchemy pydantic pydantic-settings \
            pyjwt bcrypt python-multipart pytest httpx email-validator
cd ../.. && python src/scripts/seed.py --complaints 500 --reset
cd src/backend && uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd src/frontend
npm install && npm run dev
```

Demo accounts (password `CivicPulse@2026`): `citizen@demo.local`,
`officer@demo.local`, `worker@demo.local`, `admin@demo.local`.

## 8. Known Limitations

Full, honest list: **[docs/limitations.md](docs/limitations.md)**.

In short: the dataset and ward geometry are synthetic; the risk/priority
models are unvalidated heuristics designed to be swapped for a calibrated
model later without changing their interface; verification raises the bar
for bad actors but does not defeat a determined one; and the surge
simulation demonstrates the async-processing pattern rather than standing
up a production message queue.

---

## Scaling Analysis

Assumptions: 65 wards, ~5,000 complaints/day sustained, Dasara spike up to
~50,000/day (~1.5M/month at sustained peak).

**Likely bottlenecks at that scale:** write throughput on the complaints
table during a spike; recomputing duplicate/priority/risk synchronously on
the request path; unbounded dashboard aggregate queries; evidence storage
on local disk.

**Design already in place for this:** all list/dashboard queries are
paginated (50/page default) and aggregate-only for dashboards - the browser
never loads the full complaints table; every hot query path has a matching
index; duplicate/jurisdiction lookups use an indexed bounding-box prefilter
before any exact-distance computation, keeping the candidate set small
regardless of table size.

**Documented for production, not built in the MVP:** queue-based ingestion
(SQS/Kafka) instead of synchronous scoring on request; a worker pool for
score computation; materialized/aggregated dashboard metrics refreshed on a
schedule rather than computed live; object storage + CDN for evidence
photos instead of local disk; PostGIS for geospatial queries at scale.

The Dasara surge simulator (`POST /api/demo/simulate-surge`) demonstrates
the pattern - asynchronous batch processing behind a polled status endpoint,
UI never blocks - against the *real* duplicate/priority/risk engines, at a
scale the MVP's single-process SQLite setup can actually sustain live for a
demo.

---

## Screenshots

See `docs/images/` (populate before submission - citizen report flow,
officer queue with risk explanation, public dashboard, jurisdiction
boundary-change demo, Dasara surge simulation).
