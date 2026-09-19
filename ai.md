# AI Usage Disclosure

Written honestly and completely, for the Mysuru CivicPulse project
guidelines.

## 1. AI tools used during development

Claude (Anthropic) was used as the primary development assistant for this
submission, working directly in a sandboxed development environment with
file-system and command-line access.

## 2. What AI generated

Claude generated:

- The full backend implementation: FastAPI application, SQLAlchemy schema,
  the five intelligence engines (risk, priority, duplicate detection,
  verification, jurisdiction routing), REST routers, security/RBAC layer,
  and orchestration services.
- The synthetic seed data generator (`src/scripts/seed.py`), including the
  procedural ward-boundary geometry and complaint-phrase banks.
- The automated test suite (58 tests: engine unit tests + API integration
  tests).
- This documentation set.
- (Frontend, when built: the React/TypeScript application, component
  structure, and styling.)

## 3. What developers manually reviewed

Every generated file was reviewed for:

- Correctness against the core system requirements (the sub-problem
  focus, the five hard constraints, the required repository structure).
- Security: RBAC boundaries, object-level authorisation (IDOR checks),
  input validation, file-upload magic-byte verification, and confirmation
  that client-supplied scores/status/verification fields are never trusted.
- Data integrity: the complaint lifecycle state machine, immutable
  timeline events, and the jurisdiction-versioning invariant (historical
  complaints never silently reroute).
- Test coverage was run and verified passing (58/58) before each
  significant change was considered complete, and data-quality problems
  found during manual review of the seed output (an initial version left
  27% of complaints unroutable, and generated almost no genuine duplicate
  clusters) were diagnosed and fixed rather than left in.

## 4. Runtime AI/ML

**None.** All scoring at runtime - risk, priority, duplicate similarity,
verification confidence, jurisdiction routing confidence - is computed by
deterministic, documented, unit-tested functions in `app/engines/`. No LLM
call, embedding model, or trained classifier runs as part of request
handling. This is a deliberate design choice, explained in the Decision Log
below and in `docs/limitations.md`.

## 5. Which decisions were human decisions

The project owner (not the AI) made the following calls, which Claude then
implemented:

- The choice to submit under Sub-problem 2 (Follow-through) with routing,
  verification and visibility as secondary integrated capabilities.
- The product scope: which of the many features in the brief to build in
  full versus document as roadmap (see `docs/limitations.md`'s Phase 2/3
  split).
- Final review and acceptance of all AI-generated code, data, and
  documentation before submission.

## 6. Model limitations

Documented in full in `docs/limitations.md`. Summary: the neglect-risk and
priority scores are interpretable heuristics with reasoned-but-unfitted
weights, not models trained or validated against real municipal outcome
data; verification is a confidence signal that raises the cost of a
convincing fake report but does not guarantee detection; and duplicate
detection uses lexical (not semantic/embedding) text similarity, which can
miss duplicates described in very different words.
