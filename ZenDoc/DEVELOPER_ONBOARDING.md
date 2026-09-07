---
Last verified: 2026-09-07
Evidence source: Development conventions observed consistently across this codebase's history; no separate onboarding document existed prior to this one.
---

# Developer Onboarding

[← Back to index](./README.md)

This document covers what isn't already in [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md) (getting it running) or [CODEBASE_MAP.md](./CODEBASE_MAP.md) (where things live).

## Read these five documents first, in this order

1. [SYSTEM_CONTEXT.md](./SYSTEM_CONTEXT.md) — what this even is
2. [FUNCTIONAL_CAPABILITIES.md](./FUNCTIONAL_CAPABILITIES.md) — what it does
3. [CODEBASE_MAP.md](./CODEBASE_MAP.md) — how to actually navigate the two large files
4. [DATA_MODEL.md](./DATA_MODEL.md) — especially the `customer_key` vs. phone number distinction; this has caused real bugs when missed
5. [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](./KNOWN_RISKS_AND_TECHNICAL_DEBT.md) — so you don't rediscover known gaps as if they were news, and don't build on top of the two features (Marketing "Recently created" list, Canva integration) known to be incomplete

## Conventions observed in this codebase — follow these, don't reinvent

- **Backend action names**: `snake_case`, verb-first, added as a new `case` in the one `switch` statement. Every new action needs its own `requireOwner()` (or equivalent role) check if it should be owner-only — there is no framework-level enforcement of this, it's a per-case discipline.
- **Any new WhatsApp send path must go through `approveAndSendDecision`**, not call `sendWhatsappTemplate`/`sendWhatsappText` directly, or it will silently bypass the do-not-disturb and cooldown checks. This is not optional — see [AUTHENTICATION_AND_SECURITY.md](./AUTHENTICATION_AND_SECURITY.md) for why this matters.
- **Any query against a table that could exceed ~1000 rows must use the `fetchAllPages` pattern**, not a bare `.select()`. This has caused a real production undercounting bug when skipped.
- **New tables/columns are never assumed to exist** — every schema change needs to be explicitly run (see the real gap noted in [DEPLOYMENT_RUNBOOK.md](./DEPLOYMENT_RUNBOOK.md): no migration files exist, so this currently means manually running SQL and confirming it was actually applied, not just written).
- **Verify before claiming something is fixed.** This codebase's development history shows a repeated pattern: compile-check every backend change, structurally verify every frontend change (tag balance, JS syntax), and test real user flows with a headless browser and mocked responses before considering anything done. Treat this as the working standard, not an optional extra step.

## Where to ask questions

**[UNKNOWN — no team communication channel, issue tracker, or code review process is documented anywhere in this repository or its prior context. This needs to be established, not discovered.]**

## How work has been reviewed/merged historically

**[UNKNOWN — no PR history, branch strategy, or review process is evidenced in this repository as currently structured (single files, no visible git branching conventions reviewed as part of this pass).]** This is worth resolving explicitly as part of onboarding multiple developers, per [ADR-0001-REPOSITORY-STRATEGY.md](./adr/ADR-0001-REPOSITORY-STRATEGY.md).
