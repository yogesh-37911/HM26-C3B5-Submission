# Decision Log

One entry per significant engineering decision. Convert to PDF for submission.

## Template

### Decision: <short title>
- **Date:**
- **Context:** What problem or requirement prompted this decision?
- **Options considered:**
  1. Option A - pros / cons
  2. Option B - pros / cons
- **Decision:** What was chosen.
- **Rationale:** Why, specifically.
- **Consequences:** What this makes easier or harder later.

---

## Worked example (from this project)

### Decision: Explainable rule-based scoring instead of a trained ML model
- **Date:** Hackathon build
- **Context:** Need a Neglect Risk Score and Priority Score that an officer
  can act on and contest.
- **Options considered:**
  1. Train a classifier (logistic regression / random forest) on synthetic
     labels - looks more "AI", but labels would be fabricated, and the
     model's reasoning is opaque to the officer using it.
  2. Deterministic weighted scoring engine with per-factor attribution -
     fully explainable, no training data required, same call signature a
     real model could fill later.
- **Decision:** Option 2.
- **Rationale:** A civic officer prioritising work needs to see *why* a
  complaint scored high, and an MVP has no real historical resolution data
  to fit or validate a model against. A fabricated-label model would be
  less honest than a stated heuristic.
- **Consequences:** Scores are reasoned defaults, not statistically fitted
  - documented plainly in `docs/limitations.md`. The engine interface
    (`score, level, factors, action`) is designed so a trained model can
    replace the heuristic later without touching any caller.

### Decision: Versioned jurisdiction boundaries instead of a static ward map
- **Context:** HackMysuru explicitly flags that Mysuru's boundaries are
  changing.
- **Options considered:**
  1. Hard-code `locality -> ward` - simple, but wrong the moment a
     boundary changes, and silently corrupts historical records.
  2. `Jurisdiction` (stable identity) + `JurisdictionVersion` (dated
     geometry), complaints snapshot the version they were routed under.
- **Decision:** Option 2.
- **Rationale:** History must stay correct; only future complaints should
  see a boundary change.
- **Consequences:** Slightly more schema complexity, but boundary
  republishing is now a safe, demoable admin action instead of a data
  migration.
