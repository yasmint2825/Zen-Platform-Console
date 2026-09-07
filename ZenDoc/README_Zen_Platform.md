---
Last verified: 2026-09-07
Evidence source: This document indexes the other 21 documents in this set, all produced from direct inspection of index.ts, zen-clickable-prototype.html, and mw-whatsapp-webhook-index.ts.
---

# Zen Platform — Architecture Documentation

This is the navigation index for everything in `doc/`. Every document here is evidence-based — grounded in what the actual code does, with repository-relative paths cited throughout — not generic architecture description. Gaps that couldn't be verified are marked **[UNKNOWN]** explicitly rather than filled in with a plausible guess.

## Start here if you're a new developer

Read in this order — see [DEVELOPER_ONBOARDING.md](./DEVELOPER_ONBOARDING.md) for the full reasoning behind this sequence:

1. [SYSTEM_CONTEXT.md](./SYSTEM_CONTEXT.md) — what Zen is, and the three real deployable pieces that make it up
2. [FUNCTIONAL_CAPABILITIES.md](./FUNCTIONAL_CAPABILITIES.md) — what it actually does, organized by the six real pages in the app
3. [CODEBASE_MAP.md](./CODEBASE_MAP.md) — how to navigate two very large, flat files
4. [DATA_MODEL.md](./DATA_MODEL.md) — especially the `customer_key` identity concept; getting this wrong has caused real bugs
5. [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md) → [DEVELOPER_ONBOARDING.md](./DEVELOPER_ONBOARDING.md) — getting productive

## Start here if you're planning the microservice migration

1. [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](./KNOWN_RISKS_AND_TECHNICAL_DEBT.md) — read this first; every migration decision should account for what's here
2. [CURRENT_ARCHITECTURE.md](./CURRENT_ARCHITECTURE.md) — confirms the "flat" description precisely, with real evidence
3. [TARGET_ARCHITECTURE_ALIGNMENT.md](./TARGET_ARCHITECTURE_ALIGNMENT.md) — proposed service boundaries, with confidence levels stated honestly
4. [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) — the proposed phased approach
5. [adr/](./adr/README.md) — five proposed ADRs recording the actual decisions this migration needs, for team review and formal acceptance

## Full index

| Document | Covers |
|---|---|
| [SYSTEM_CONTEXT.md](./SYSTEM_CONTEXT.md) | What Zen is, who uses it, the three real deployable units and how they connect |
| [FUNCTIONAL_CAPABILITIES.md](./FUNCTIONAL_CAPABILITIES.md) | Everything the product does, by page |
| [CURRENT_ARCHITECTURE.md](./CURRENT_ARCHITECTURE.md) | The real, as-built architecture — request flows, deployment topology, internal patterns |
| [CODEBASE_MAP.md](./CODEBASE_MAP.md) | Where things live in two large, flat files, and how to read them |
| [DATA_MODEL.md](./DATA_MODEL.md) | 72 real tables, grouped, with the one identity concept every developer must understand |
| [API_AND_INTEGRATIONS.md](./API_AND_INTEGRATIONS.md) | The single action-routed internal API, and every real external integration |
| [AUTHENTICATION_AND_SECURITY.md](./AUTHENTICATION_AND_SECURITY.md) | Auth, tenant isolation, credential handling, and the AI safety gating |
| [JOBS_AND_SCHEDULES.md](./JOBS_AND_SCHEDULES.md) | Confirmed scheduled/cron work and GitHub Actions workflows |
| [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md) | Environment variables, and what is/isn't documented for running this locally |
| [DEPLOYMENT_RUNBOOK.md](./DEPLOYMENT_RUNBOOK.md) | The real (manual) deploy process, and a genuine, repeated deployment-drift risk |
| [TESTING_STRATEGY.md](./TESTING_STRATEGY.md) | Honest: zero automated tests exist; what verification process was used instead |
| [OBSERVABILITY_AND_OPERATIONS.md](./OBSERVABILITY_AND_OPERATIONS.md) | Logging, the real health-check action, and cost observability |
| [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](./KNOWN_RISKS_AND_TECHNICAL_DEBT.md) | Every confirmed real gap, ranked by severity — the most important document here |
| [TARGET_ARCHITECTURE_ALIGNMENT.md](./TARGET_ARCHITECTURE_ALIGNMENT.md) | Proposed mapping from current capabilities to a target service architecture |
| [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) | Proposed phased, incremental migration sequence |
| [DEVELOPER_ONBOARDING.md](./DEVELOPER_ONBOARDING.md) | Conventions to follow, and what's still unresolved about team process |
| [adr/](./adr/README.md) | Five proposed Architecture Decision Records |

## A note on how this documentation was produced

This set was generated from direct inspection of the three real source files in this repository — no architecture documentation existed before it. Every non-trivial claim is either cited to a specific file/pattern, or marked **[UNKNOWN]** where it could not be verified from the code alone. Grep for `[UNKNOWN]` across this directory to find every open item that needs a real answer from the team rather than an assumption.
