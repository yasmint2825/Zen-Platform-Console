---
Last verified: 2026-09-07
Evidence source: CURRENT_ARCHITECTURE.md, DEPLOYMENT_RUNBOOK.md
---

# ADR-0001: Repository Strategy

[← Back to ADR index](./README.md)

**Status: Proposed**

## Context

This project (`yasmint2825/Zen-Platform-Console`) currently lives in its own single-purpose GitHub repository: three source files, no folder structure, no shared tooling with any other project. A second, related project (referred to as the Loyalty Passport app) is being onboarded alongside it, sharing the same live Supabase database but otherwise developed and deployed independently — see [SYSTEM_CONTEXT.md](../SYSTEM_CONTEXT.md). Both need to be brought into a new GitHub organization/repository structured around a microservice-based SaaS architecture, with multiple developers able to work across both.

## Decision (proposed)

Adopt a **monorepo** for the new architecture, with this project and the Loyalty Passport project onboarded as separate top-level directories initially (effectively a "polyrepo inside a monorepo" transitional state), migrating toward genuine per-service directories as [MIGRATION_PLAN.md](../MIGRATION_PLAN.md)'s phases extract real services.

Concretely:
```
new-repo/
├── legacy/
│   ├── zen-platform-console/   # this project, onboarded as-is initially
│   └── loyalty-passport/       # the sibling project, onboarded as-is initially
├── services/                   # new, extracted microservices land here as Migration Plan phases complete
│   └── (empty initially)
├── doc/                        # cross-project architecture docs (this document set, consolidated)
└── shared/                     # cross-cutting concerns identified during migration (e.g. the AI Gateway question — see MIGRATION_PLAN.md)
```

## Alternatives considered

- **Polyrepo (separate repos per eventual service).** Rejected for the *initial* onboarding specifically because no service boundaries are decided yet ([ADR-0002](./ADR-0002-SERVICE-BOUNDARIES.md) is still Proposed) — creating separate repos before boundaries are settled risks having to re-split them later. Revisit once Phase 1-2 of the migration plan validate real boundaries.
- **Keep both projects in their existing separate repos, coordinate via a meta-repo or documentation only.** Rejected because it does nothing to enable the stated objective of multiple developers working across both — cross-repo changes (e.g. a shared AI Gateway) would require coordinating PRs across repos with no atomic commit boundary.
- **Immediate full microservice extraction with per-service repos from day one.** Rejected as too high-risk given zero test coverage on the current codebase ([KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md)) — extracting into separate repos before understanding real coupling (see [TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md)'s "does not map cleanly" section) would lock in guesses as physical boundaries prematurely.

## Consequences

- The `legacy/` directories initially retain the exact flat structure documented in [CODEBASE_MAP.md](../CODEBASE_MAP.md) — no internal refactor required to onboard.
- Both projects' existing deployment mechanisms (manual `supabase functions deploy`, per [DEPLOYMENT_RUNBOOK.md](../DEPLOYMENT_RUNBOOK.md)) continue to work unchanged during the transitional period — CI/CD for the monorepo needs to be scoped to trigger the correct deploy per changed path, not deploy everything on every change.
- **[UNKNOWN — the Loyalty Passport project's own architecture, deployment mechanism, and test coverage were not evidenced in this documentation pass. This ADR assumes a similar profile (flat, undocumented, manually deployed) based only on it being described as sharing this project's development history; confirm directly before finalizing this decision.]**
