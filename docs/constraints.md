# Constraints

Direct answers to the five hard constraints in the HackMysuru problem
statement.

## 1. People will lie

We assume some fraction of reports are spam, exaggerated, or fabricated, and
we do not pretend to solve this perfectly.

- **Verification pipeline** (`app/engines/verification.py`) scores every
  report 0-100 from six independent signals: coordinate plausibility,
  description completeness, evidence presence, reused-image-hash detection,
  submission-rate throttling, and independent corroboration from nearby
  reports. The result is one of `VERIFIED / PLAUSIBLE / NEEDS_REVIEW /
  SUSPICIOUS`.
- **Nothing is ever silently deleted.** The worst outcome for a report is
  `SUSPICIOUS`, which routes it to a human queue - not rejection. A citizen
  whose genuine report is wrongly flagged still has a record and a tracking
  ID.
- **Duplicate detection** (below) means a real, corroborated issue naturally
  accumulates trust as more citizens independently report it.
- The UI states plainly: "Verification is a confidence signal, not proof."
  We do not claim to detect a determined false report reliably, and the
  `ai.md` / `docs/limitations.md` files say so explicitly.

## 2. Jurisdiction is changing

- Boundaries are modelled as **`Jurisdiction` (stable identity) +
  `JurisdictionVersion` (geometry with an effective date range)**, not a
  hard-coded mapping. See `docs/architecture.md` for the schema.
- Routing (`app/engines/jurisdiction.py`) always resolves a coordinate
  against whichever boundary version was **active at the time the complaint
  was filed** (or "now" for a fresh lookup). A complaint stores the specific
  `jurisdiction_version_id` it was routed under, so republishing a boundary
  never rewrites history.
- The admin console (and `POST /api/jurisdictions/version`) lets an admin
  publish a new boundary version with its own effective date. Old complaints
  keep their original routing; only complaints filed after the new version's
  `effective_from` are affected. This is demonstrated end-to-end in
  `tests/test_api.py::test_boundary_version_change_affects_only_new_complaints`
  and in the seed data (Ward 42 has a staged revision).

## 3. Complaints have different urgency

- The **priority engine** (`app/engines/priority.py`) is separate from the
  **neglect risk engine** (`app/engines/risk.py`) - they answer different
  questions ("what should be fixed first?" vs "what is about to be
  forgotten?").
- Priority weighs intrinsic severity, direct public-safety impact, proximity
  to a school/hospital/junction, complaint age, and a **capped** report-volume
  term (15 of 100 points, by design) so a heavily-reported cosmetic issue
  cannot mathematically outrank a genuine hazard. A safety override further
  guarantees a severe hazard next to a school or hospital is never shown as
  MEDIUM or LOW.
- Every score ships with per-factor attribution ("Why this priority?") so an
  officer can see and contest the reasoning, not just a number.

## 4. Bad / tricky inputs

Demonstrated live via `GET /api/demo/scenarios` and
`POST /api/demo/scenario/{key}`, which run the actual production engines
against a crafted input (not a canned response):

- **Duplicate report** - geospatial + textual + temporal similarity scoring;
  the citizen is shown the existing complaint and chooses to follow it or
  file separately. Category is a hard gate (a pothole and a streetlight at
  the same corner are never proposed as duplicates).
- **Wrong / impossible location** - coordinates outside the Mysuru service
  area fail the plausibility check and cannot be routed; the report is
  queued for manual review, not silently discarded.
- **Suspicious repeated evidence** - a reused SHA-256 image hash drops trust
  to `SUSPICIOUS` and flags for human review.
- **Missing photo** - allowed; verification is downgraded and neglect risk
  ticks up slightly (evidence-free reports need a site visit to confirm).
- **Incomplete report** - a description under ~5 words is marked
  `NEEDS_REVIEW`, not rejected.
- **Unusual input** - server-side Pydantic validation rejects out-of-range
  coordinates, oversized payloads, and unknown categories with field-level
  422 errors; file uploads are checked by magic bytes, not just the
  client-declared MIME type.

## 5. Detection / operational reality

Mysuru does not have (and this project does not assume) city-wide sensor
coverage or CCTV analytics. CivicPulse deliberately does not attempt
automatic issue detection - it focuses on follow-through once a human
(citizen or field worker) has reported something:

- Citizen reports are the primary evidence source, corroborated by
  duplicate/independent reports from other citizens.
- Field workers supply the second evidence layer (photo + notes) as they
  physically verify and resolve issues.
- The neglect-risk engine's whole purpose is to catch complaints that would
  otherwise be forgotten between these two human touchpoints - it does not
  claim to discover issues no one has reported.
