# Resource Index - Mysuru CivicPulse

Central landing file for reviewers. Fill in the placeholders below before final submission.

## Project

- **Project title:** Mysuru CivicPulse
- **Team ID:** `HM26-C3B5`
- **Sub-problem:** SUB-PROBLEM 2 - Follow-through (with Routing, Verification, Visibility integrated)

## Links

- **Live demo URL:** <https://mysuru-pulse.onrender.com>
- **GitHub repository URL:** <https://github.com/yogesh-37911/HM26-C3B5-Submission.git>

- **Demo video URL:** <https://drive.google.com/file/d/1jjCTBL7PrHxPUSE_--pFWkwRzSA_QC0D/view?usp=drive_link>
- **Demo video SHA-256:** `221C75950502E980`

- **Coding walkthrough video URL:** <https://drive.google.com/file/d/1j9wGmBQ1th_puqV6_URHQnbwp8ZzjDbM/view?usp=drive_link>

- **Decision log PDF:** <https://drive.google.com/file/d/1PxT2nKwRqM7u_1JYiwuwsGBOyQY4pzA6/view?usp=sharing>
- **Decision log SHA-256:** `E22962781900B03B`

- **Presentation PDF:** <https://drive.google.com/file/d/1M13pVLY9oMEygzCYxbzNvGmrcbHV-cc8/view?usp=drive_link>
- **Presentation PDF SHA-256:** `2BF808A4551C94C2`

## Documentation

| Document | Path |
| --- | --- |
| Problem understanding, solution overview, decision log summary | [README.md](README.md) |
| AI usage disclosure | [ai.md](ai.md) |
| System architecture, diagrams, schema | [docs/architecture.md](docs/architecture.md) |
| Hard-constraint responses | [docs/constraints.md](docs/constraints.md) |
| Known limitations & roadmap | [docs/limitations.md](docs/limitations.md) |
| Setup & run instructions | [docs/setup.md](docs/setup.md) |

## Demo Credentials

All demo accounts share the password `CivicPulse@2026` (configurable via the `DEMO_PASSWORD` environment variable before seeding).

| Role | Email |
| --- | --- |
| Citizen | `citizen@demo.local` |
| Officer (MCC Ward 42) | `officer@demo.local` |
| Field worker (MCC Ward 42) | `worker@demo.local` |
| Admin | `admin@demo.local` |

## AI Disclosure

See [ai.md](ai.md) for the full, itemised disclosure.

Summary: AI (Claude) was used as the primary development assistant for backend, data generation, tests, frontend, and documentation. All runtime scoring is deterministic (no AI/ML runs during request handling), and all output was human-reviewed before submission.

## Verification

SHA-256 hashes of final external deliverables:

```text
demo-video.mp4:        221C75950502E980
decision-log.pdf:      E22962781900B03B
presentation.pdf:      2BF808A4551C94C2
