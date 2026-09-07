---
Last verified: 2026-09-07
Evidence source: MIGRATION_PLAN.md, KNOWN_RISKS_AND_TECHNICAL_DEBT.md
---

# ADR-0005: Incremental Migration

[← Back to ADR index](./README.md)

**Status: Proposed**

## Context

The current system is a live, revenue-affecting production system (a real business's WhatsApp messaging, customer data, and ad spend run through it today) with zero automated test coverage ([KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md), item 1). Any migration approach needs to account for the real risk of breaking live customer-facing functionality (WhatsApp opt-out enforcement, for one concrete example, has already had one confirmed production gap during this system's development) with no automated safety net to catch a regression before it reaches customers.

## Decision (proposed)

Adopt the phased approach detailed in [MIGRATION_PLAN.md](../MIGRATION_PLAN.md): Foundations (testing + schema versioning + environment separation) → Ads → Content → Messaging/Campaign/Customer Intelligence → retire monolithic paths — each phase independently shippable, none requiring the full target architecture to be decided upfront (see [ADR-0002](./ADR-0002-SERVICE-BOUNDARIES.md)'s explicit deferral of the hardest boundary decision).

**"Done" for each phase** means: the extracted service handles 100% of its capability's real traffic, the equivalent `case` blocks are confirmed unused (not yet deleted — see Phase 4), and the specific risk called out for that phase in [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) has been directly addressed, not just "the code compiles and a manual smoke test passed."

**Rollback strategy per phase:** each extracted service reads/writes the *same* tables the monolith already uses (per [ADR-0003](./ADR-0003-DATA-OWNERSHIP.md)) rather than forking data into a new store during extraction — this means rollback is "route traffic back to the monolith's existing action," not "migrate data back," for every phase except Phase 4 (where the monolithic path being retired is the rollback target, and must not be deleted until the team is genuinely confident, not just after the extracted service has been live for a fixed time period).

## Alternatives considered

- **A full rewrite into the target microservice architecture, then cut over.** Rejected outright — this is explicitly the pattern [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) and this ADR are designed to avoid, given the system's live production status and zero test coverage make a big-bang cutover the highest-risk option available, not a shortcut.
- **Strangler-fig pattern with a routing layer in front of both old and new systems from day one.** This is very close to what's proposed, and arguably a more precise name for it. Not rejected — genuinely the same underlying approach as the phased plan, just without a dedicated routing-layer component named explicitly. Worth naming and building deliberately (a real reverse-proxy/routing layer, not just "the frontend calls whichever URL is currently correct") as part of Phase 0, rather than left implicit.
- **Migrate by team/developer assignment rather than by capability.** Rejected as the primary sequencing axis — capability-based sequencing (per [MIGRATION_PLAN.md](../MIGRATION_PLAN.md)) is grounded in actual coupling evidence from the code; assigning phases by which developer is available doesn't account for the real dependency risk between clusters (e.g. the AI Gateway question blocking Phase 2).

## Consequences

- This is a genuinely slower path than a rewrite — accepted deliberately, given the alternative's risk profile against a live, revenue-affecting system with no automated tests.
- Phase 0 must actually happen, not be skipped under time pressure to "get to the real work" — every subsequent phase's rollback safety and confidence level depends on it.
- The monolith (`index.ts`) remains the deployed source of truth for any capability not yet fully migrated, for the entire duration of this plan — it should not be treated as legacy-and-frozen until Phase 4 actually retires each specific capability, since bug fixes to not-yet-migrated capabilities still need to land there.
