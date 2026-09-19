# Setup & Run

This project is designed to work from a clean machine with **zero external
services required** — SQLite is the default database, so there is nothing to
install beyond Node and Python.

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ (developed on 3.12) |
| Node.js | 18+ (developed on 22) |
| npm | bundled with Node |

No Postgres, Docker, or paid API keys are required for the default setup.

## 1. Clone and enter the repo

```bash
cd Mysuru-Pulse
```

## 2. Backend setup

```bash
cd src/backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install fastapi "uvicorn[standard]" sqlalchemy pydantic pydantic-settings \
            pyjwt bcrypt python-multipart pytest httpx email-validator

cp ../../.env.example .env       # edit if you want Postgres instead of SQLite
```

## 3. Seed the database

From the **repository root**:

```bash
python src/scripts/seed.py --complaints 500 --reset
```

This creates the SQLite file, all 65 MCC wards + 5 peripheral panchayats,
categories, demo SLA rules, demo accounts, and 500 synthetic complaints with
realistic status/age/duplicate distributions. It also stages a boundary
revision for MCC Ward 42 effective 13 days from when you seed, for the
jurisdiction-versioning demo (see "Demo: boundary versioning" below).

Re-running the seed without `--reset` is a no-op if data already exists; use
`--reset` to rebuild from scratch.

## 4. Run the backend

```bash
cd src/backend
uvicorn app.main:app --reload --port 8000
```

- API root: http://localhost:8000
- Interactive API docs (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

## 5. Frontend setup

```bash
cd src/frontend
npm install
cp .env.example .env             # VITE_API_URL defaults to localhost:8000
npm run dev
```

Open http://localhost:5173.

## 6. Demo credentials

All demo accounts share the password: **`CivicPulse@2026`** (or whatever you
set as `DEMO_PASSWORD` before seeding).

| Role | Email |
|---|---|
| Citizen | `citizen@demo.local` |
| Officer (Ward 42) | `officer@demo.local` |
| Field worker (Ward 42) | `worker@demo.local` |
| Admin | `admin@demo.local` |

## 7. Running tests

```bash
cd src/backend
python -m pytest tests -q
```

The test suite reseeds its own throwaway SQLite database (150 complaints) on
first run — it does not touch your development database. 58 tests cover the
engines (pure-function unit tests), auth/RBAC, the complaint lifecycle, the
jurisdiction-versioning behaviour, duplicate detection, offline sync
idempotency, and the demo endpoints.

## 8. Demo features

**Bad-input scenarios** (judges' panel): `GET /api/demo/scenarios` lists them;
`POST /api/demo/scenario/{key}` runs the real engines against a crafted input
and returns the result. In the frontend this is the "Demo / Test" panel in
the admin console.

**Dasara surge simulation**: `POST /api/demo/simulate-surge` with
`{"count": 5000}` starts an asynchronous batch worker; poll
`GET /api/demo/surge/{run_id}` for live progress. The frontend's Load
Simulation page polls this automatically.

**Boundary versioning**: the seed script stages a Ward 42 boundary revision
13 days in the future. To demo it immediately, use the admin console's
"Jurisdiction Versions" page to publish a new version with an
`effective_from` of "now", or call:

```bash
curl -X POST http://localhost:8000/api/jurisdictions/version \
  -H "Authorization: Bearer <admin-token>" -H "Content-Type: application/json" \
  -d '{"jurisdiction_id": 42, "version_label": "demo-now", "effective_from": "2020-01-01T00:00:00Z", "boundary": [[12.28,76.615],[12.29,76.615],[12.29,76.625],[12.28,76.625]], "close_previous": true}'
```

Then compare `GET /api/complaints/{id}/jurisdiction` for an old complaint
(unchanged) against `GET /api/jurisdictions/resolve?lat=...&lng=...` for the
same point today (changed).

## 9. Production build

```bash
# Backend: run behind a real ASGI server, e.g.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Frontend
cd src/frontend
npm run build      # outputs to src/frontend/dist
npm run preview    # sanity-check the production build locally
```

Set `ENV=production` and a real random `JWT_SECRET` before deploying — the
app refuses to start in production with the default development secret.

## 10. Switching to Postgres / Supabase

Set `DATABASE_URL` in `.env` to a Postgres DSN, e.g.:

```
DATABASE_URL=postgresql+psycopg://user:password@host:5432/civicpulse
pip install psycopg[binary]
```

No code changes are required — SQLAlchemy handles the dialect switch. Note
that the geospatial queries use plain lat/lng bounding boxes rather than
PostGIS (see `docs/limitations.md`); this works identically on both engines.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `email-validator is not installed` | `pip install email-validator` |
| `password cannot be longer than 72 bytes` | Already handled — passwords are truncated to 72 bytes before hashing (bcrypt's own limit). If you see this, you're on an old checkout; pull latest. |
| Frontend can't reach the API | Check `VITE_API_URL` in `src/frontend/.env` matches where uvicorn is running, and that `CORS_ORIGINS` in the backend `.env` includes the frontend's origin. |
| `Illegal transition` errors while testing status changes | The lifecycle is a state machine (see `docs/architecture.md`); not every status can move to every other status. This is intentional. |
| Seed script says data already exists | Pass `--reset` to rebuild, or delete `civicpulse.db`. |
