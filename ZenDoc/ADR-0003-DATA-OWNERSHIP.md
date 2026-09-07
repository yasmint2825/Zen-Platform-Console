---
Last verified: 2026-09-07
Evidence source: DATA_MODEL.md (72 tables catalogued from index.ts queries)
---

# ADR-0003: Data Ownership

[← Back to ADR index](./README.md)

**Status: Proposed**

## Context

All 72 tables identified in [DATA_MODEL.md](../DATA_MODEL.md) live in one Supabase Postgres database today, queried directly by the one monolithic backend with no data-access boundary beyond `tenant_id` row filtering and RLS. [ADR-0002](./ADR-0002-SERVICE-BOUNDARIES.md) proposes six services; each will need clarity on which tables it owns versus which it must access through another service's API.

## Decision (proposed)

**Tables are owned by the service proposed in [TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md)'s per-capability mapping**, with cross-service access via synchronous API call in the near term (matching how [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) Phase 1 proposes handling Custom Audience creation's read of Customer Intelligence data), not shared direct database access and not an event bus — a synchronous call is the smallest change from current behavior and the easiest to reason about and roll back during an incremental migration.

The genuinely un-prefixed tables (`customers`, `assets`, `generations`, `content_plan_items`, `creative_briefs`, `brand_profiles`, `brand_rules`, `business_strategy`, `monthly_content_strategy`, `historical_transactions` — see [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md), item 6) must have their ownership explicitly resolved **before** Phase 2 (Content extraction) begins, since most of them are Content-cluster tables and their inconsistent naming suggests they were not designed with a clean ownership boundary in mind.

## Alternatives considered

- **Shared database, no ownership boundary, every service queries every table it needs directly.** This is effectively the status quo. Rejected as the target state because it defeats the purpose of service extraction — a "microservice" that still directly queries another service's tables has a hidden coupling that will resurface the moment either service's schema needs to change independently.
- **Event-driven data replication (each service maintains its own copy of data it needs from another service, kept in sync via events).** Rejected for the *initial* migration specifically — it's the architecturally "purer" answer but introduces eventual consistency and a new class of bugs (stale replicated data) into a codebase that currently has zero automated test coverage to catch them ([KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md), item 1). Revisit once Phase 0's testing foundation is in place and the team has operating experience with synchronous cross-service calls.
- **A shared "core data" service that every other service reads from directly (not through domain-specific services).** Considered for Customer Intelligence specifically, since [TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md) notes its data is read by nearly everything. Not rejected outright — this is a reasonable variant of the decision above and worth revisiting once Phase 3 of the migration plan is reached, since it may better fit the read-heavy, write-light pattern Customer Intelligence data actually has.

## Consequences

- Every cross-service data access becomes a real network call with real latency and real failure modes that don't exist today (a same-process function call cannot time out or return a 5xx the way an HTTP call can) — this must be designed for explicitly in each service's API, not discovered in production.
- The un-prefixed tables' true ownership needs a real decision, not an assumption, before Phase 2 — recorded as an open item here rather than silently resolved by whichever service happens to touch a table first during extraction.
- No new migration tooling exists yet ([KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md), item 2) — this must be solved as part of Phase 0 before any table ownership can be safely enforced (e.g. via separate database credentials per service, or schema-level permissions), since there is currently no way to even know the full current schema with confidence.
