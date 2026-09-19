# Architecture

## System overview

```mermaid
flowchart LR
    subgraph Client["Frontend (React + Vite + TS)"]
        Citizen[Citizen App]
        Officer[Officer Dashboard]
        Field[Field Worker App]
        Public[Public Dashboard]
    end

    subgraph API["Backend (FastAPI)"]
        Auth[Auth / RBAC]
        Routers[REST Routers]
        Engines["Intelligence Engines\n(risk, priority, duplicate,\nverification, jurisdiction, SLA)"]
        Services[Orchestration Services]
    end

    DB[(PostgreSQL / SQLite)]
    Files[(Evidence Store)]

    Citizen -->|REST + JWT| Auth
    Officer -->|REST + JWT| Auth
    Field -->|REST + JWT + offline queue| Auth
    Public -->|REST, unauthenticated| Routers

    Auth --> Routers --> Services --> Engines
    Services --> DB
    Routers --> Files
```

## Component responsibilities

| Layer | Location | Responsibility |
|---|---|---|
| Routers | `app/routers/*.py` | HTTP concerns only: parse/validate request, check role, call a service, shape the response. |
| Services | `app/services/*.py` | Orchestration: load rows, call engines, write timeline events, commit. `complaint_service.intake()` is the main pipeline. |
| Engines | `app/engines/*.py` | Pure functions, no DB/IO. Given plain inputs, return a score + explanation. Independently unit-tested. |
| Models | `app/models.py` | SQLAlchemy schema, the state-machine transition table, enums. |
| Security | `app/security.py` | Password hashing, JWT issue/verify, RBAC dependency, jurisdiction-scoped authorisation. |

Keeping engines pure was a deliberate boundary: a router can be wrong about
auth, a service can be wrong about ordering, but a risk score is either
correctly computed from its inputs or it isn't — testing that in isolation,
with no database fixture, is what makes 30+ engine tests fast and reliable.

## Data flow: complaint intake

```mermaid
sequenceDiagram
    participant C as Citizen App
    participant API as FastAPI
    participant V as Verification Engine
    participant D as Duplicate Engine
    participant J as Jurisdiction Engine
    participant P as Priority Engine
    participant R as Risk Engine
    participant DB as Database

    C->>API: POST /api/complaints
    API->>D: find_duplicates(lat, lng, text, category)
    D-->>API: candidate matches (bbox-prefiltered, category-gated)
    API->>DB: insert Complaint (status=SUBMITTED)
    API->>J: route_complaint(lat, lng, at=now)
    J-->>API: authority, ward, boundary_version, confidence
    API->>V: verify_report(...)
    V-->>API: VERIFIED/PLAUSIBLE/NEEDS_REVIEW/SUSPICIOUS + factors
    API->>P: compute_priority(...)
    P-->>API: score, level, factors
    API->>R: compute_risk(...)
    R-->>API: score, level, factors, recommended_action
    API->>DB: write immutable timeline events (one per step)
    API-->>C: complaint + full analysis payload
```

Every automated decision in this flow writes a `ComplaintStatusHistory` row
with an event type, a human-readable note, and the full factor payload —
this is what the "public transparency" and "explainable AI" requirements
both come from the same table.

## Complaint lifecycle (state machine)

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> VALIDATING
    SUBMITTED --> ROUTED
    SUBMITTED --> REJECTED
    VALIDATING --> ROUTED
    VALIDATING --> REJECTED
    ROUTED --> ASSIGNED
    ROUTED --> REJECTED
    ASSIGNED --> IN_PROGRESS
    ASSIGNED --> ROUTED
    ASSIGNED --> REJECTED
    IN_PROGRESS --> FIELD_VERIFIED
    IN_PROGRESS --> ASSIGNED
    IN_PROGRESS --> RESOLVED
    FIELD_VERIFIED --> RESOLVED
    FIELD_VERIFIED --> IN_PROGRESS
    RESOLVED --> REOPENED
    REOPENED --> ASSIGNED
    REOPENED --> ROUTED
    REOPENED --> IN_PROGRESS
    REJECTED --> REOPENED
```

Transitions are enforced server-side by `ALLOWED_TRANSITIONS` in
`app/models.py`; an illegal transition returns `409 Conflict` naming the
allowed set. Field workers can only reach `FIELD_VERIFIED` — closing a
complaint as `RESOLVED` is reserved for officers/admins (separation of
duties).

## Risk engine

```mermaid
flowchart TD
    A[Complaint] --> B{Status closed?}
    B -->|yes| Z[Risk = 0, LOW]
    B -->|no| C[Inactivity vs SLA window - 26pts]
    A --> D[Historical delay for category/ward - 20pts]
    A --> E[Assignment gap - 18pts]
    A --> F[Complaint age vs SLA - 14pts]
    A --> G[Repeat pressure: dup+followup+reopen - 12pts]
    A --> H[Severity + safety impact - 10pts]
    C & D & E & F & G & H --> I[Sum, clamp 0-100]
    I --> J{Score >= 70?}
    J -->|yes| K[HIGH]
    J -->|no| L{Score >= 40?}
    L -->|yes| M[MODERATE]
    L -->|no| N[LOW]
```

## Priority engine

```mermaid
flowchart TD
    A[Complaint] --> B[Severity - 25pts]
    A --> C[Safety impact - 20pts]
    A --> D[Sensitive-location proximity - 15pts]
    A --> E["Report volume (CAPPED) - 15pts"]
    A --> F[Age vs SLA - 15pts]
    A --> G[Recurring location - 10pts]
    B & C & D & E & F & G --> H[Sum, clamp 0-100]
    H --> I{"Safety override:\nsafety>=3 AND\nnear school/hospital?"}
    I -->|yes, and level < HIGH| J[Force HIGH]
    I -->|no| K[CRITICAL/HIGH/MEDIUM/LOW by threshold]
```

## Duplicate detection

```mermaid
flowchart LR
    A[New report: lat, lng, text, category] --> B["SQL bbox prefilter\n(indexed lat/lng)"]
    B --> C{Same category?}
    C -->|no| X[Excluded - hard gate]
    C -->|yes| D[Haversine distance]
    C -->|yes| E[Text similarity\nJaccard + trigram Dice]
    C -->|yes| F[Temporal proximity]
    D & E & F --> G["similarity =\n0.45*spatial + 0.40*text + 0.15*temporal"]
    G --> H{similarity >= 0.55\nAND distance < 150m?}
    H -->|yes| I[Surface as candidate]
    H -->|no| X
```

## Jurisdiction routing (versioned)

```mermaid
erDiagram
    JURISDICTION ||--o{ JURISDICTION_VERSION : has
    JURISDICTION_VERSION ||--o{ COMPLAINT : "routes (snapshot)"
    JURISDICTION {
        int id
        string authority
        string authority_type
        int ward_number
    }
    JURISDICTION_VERSION {
        int id
        string version_label
        datetime effective_from
        datetime effective_to
        json boundary_json
        float min_lat
        float max_lat
        float min_lng
        float max_lng
    }
    COMPLAINT {
        int id
        int jurisdiction_id
        int jurisdiction_version_id
        float routing_confidence
    }
```

A complaint stores `jurisdiction_version_id` at the moment it is routed.
Publishing a new `JurisdictionVersion` (with its own `effective_from`) never
touches existing complaint rows — `GET /api/complaints/{id}/jurisdiction`
explicitly returns both "as filed" (historical) and "if filed today"
(current) so the effect of a boundary change is visible, not just asserted.

## Authentication & authorisation

- **JWT** (HS256), issued on login, carrying `sub` (user id), `role`, and
  `jur` (home jurisdiction, if any). 12-hour default expiry.
- **RBAC** via `require_roles(*roles)` dependency — a citizen hitting an
  officer-only route gets `403`, not a filtered response.
- **Object-level authorisation** (IDOR guard): every `GET/PATCH
  /api/complaints/{id}` loads the row first, then checks the *loaded row's*
  citizen/jurisdiction against the caller — never a client-supplied claim.
  Officers are scoped to their home jurisdiction unless it is `null`
  (city-wide officer).
- Passwords are hashed with bcrypt (cost 12), truncated to 72 bytes per
  bcrypt's own limit — done explicitly so a long passphrase degrades
  gracefully instead of 500ing.

## Offline sync

```mermaid
sequenceDiagram
    participant App as Field Worker App (offline)
    participant Queue as Local IndexedDB queue
    participant API as POST /api/field-worker/sync

    App->>Queue: enqueue action {idempotency_key, type, payload}
    Note over App: network unavailable
    App-->>App: show "3 actions pending sync"
    Note over App: network returns
    App->>API: POST /sync {actions: [...]}
    API->>API: for each action: has idempotency_key been applied before?
    API-->>App: {applied, skipped, failed}
    App-->>App: "Synced successfully"
```

Replaying the same queue twice (a common flaky-connection scenario where the
response is lost but the request landed) applies each action exactly once,
because the server checks `idempotency_key` against `offline_sync_queue`
before doing anything.

## Database schema

All 18+ tables described in the brief are implemented in
`src/backend/app/models.py`: `users`, `jurisdictions`,
`jurisdiction_versions`, `categories`, `sla_rules`, `complaints`,
`complaint_status_history`, `complaint_evidence`, `complaint_followups`,
`assignments`, `duplicate_clusters`, `duplicate_candidates`, `risk_scores`,
`priority_scores`, `audit_logs`, `notifications`, `offline_sync_queue`,
`simulation_runs`.

Key indexes: `complaints(created_at)`, `complaints(status)`,
`complaints(category_id)`, `complaints(jurisdiction_id)`,
`complaints(latitude, longitude)`, plus a composite
`(status, risk_score, priority_score)` index for the officer queue's
default sort and `(jurisdiction_id, status)` for ward-scoped queries.
`jurisdiction_versions` is indexed on its bounding box columns for the SQL
prefilter used by both routing and duplicate detection.

## API architecture

REST, versioned implicitly by path (`/api/...`), JSON in/out. Full route
list and schemas are auto-generated at `/docs` (Swagger UI) from the FastAPI
app. Priority, risk, verification, jurisdiction and status are **always**
server-computed — request schemas (`app/schemas.py`) simply do not include
fields for them, so a client cannot inject a fake score even if it tries
(see `test_server_ignores_client_supplied_scores`).

## Security architecture

- Every input is validated server-side via Pydantic (`app/schemas.py`),
  including a length-and-pattern-bounded email field, control-character
  stripping on free text, and range checks on coordinates.
- File uploads are checked against both declared MIME type and actual magic
  bytes; stored filenames are derived from the content hash, eliminating
  path traversal from user-supplied filenames.
- CORS is restricted to configured origins; security headers
  (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) are set on
  every response.
- Every officer/admin mutation writes an `AuditLog` row with before/after
  state and actor.

## Scaling architecture

See the "Scaling analysis" section of `README.md` for the sizing assumptions
(65 wards, 5,000/day sustained, 50,000/day Dasara peak) and the identified
bottlenecks. For the MVP, the Dasara surge is simulated as an in-process
background task with batched processing and a polled status endpoint,
specifically so the UI never blocks on it — the production path
(queue-based ingestion, worker pool, materialized dashboard aggregates) is
documented as future work in `docs/limitations.md` rather than built, since
a 72-hour hackathon MVP should demonstrate the *pattern*, not stand up a
message broker.
