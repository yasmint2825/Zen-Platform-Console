---
Last verified: 2026-09-07
Evidence source: N/A — this index describes the ADRs below, all newly drafted in this documentation pass.
---

# Architecture Decision Records

[← Back to doc index](../README.md)

An ADR records a significant architectural decision, the context that drove it, the alternatives considered, and its consequences — so a future developer (including a future version of the person who wrote it) understands *why*, not just *what*.

**All five ADRs below are Proposed, not Accepted.** The current architecture (see [CURRENT_ARCHITECTURE.md](../CURRENT_ARCHITECTURE.md)) is flat and has no pre-existing architectural decisions of this kind — these are genuine proposals for the team to review, amend, and formally accept or reject, drafted from evidence in the current codebase rather than presented as settled.

| ADR | Decision | Status |
|---|---|---|
| [ADR-0001](./ADR-0001-REPOSITORY-STRATEGY.md) | Repository strategy for onboarding this project into the new architecture | Proposed |
| [ADR-0002](./ADR-0002-SERVICE-BOUNDARIES.md) | Service boundaries for the target microservice architecture | Proposed |
| [ADR-0003](./ADR-0003-DATA-OWNERSHIP.md) | Data ownership per service | Proposed |
| [ADR-0004](./ADR-0004-AUTHENTICATION-AND-TENANT-ISOLATION.md) | Authentication and tenant isolation across services | Proposed |
| [ADR-0005](./ADR-0005-INCREMENTAL-MIGRATION.md) | Incremental migration approach | Proposed |

Once reviewed, update each ADR's status to Accepted, Rejected, or Superseded — don't leave them marked Proposed indefinitely once a real decision has been made.
