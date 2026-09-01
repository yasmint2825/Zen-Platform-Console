# ADR-0002: Service Boundaries

**Status:** Proposed
**Date:** 2026-09-01

## Context

`mw-admin` is 11,810 lines with 221 actions behind one `switch`. There are no
module boundaries, no way to reason about blast radius, and cold starts cost 1–2
seconds. It is the main obstacle for a new developer.

The stated objective is a "microservice-based architecture".

## Decision

**Modules inside one deployable service — not separate microservices.**

| Module | Owns |
|---|---|
| `identity` | Tenants, users, roles, API keys |
| `customers` | Profiles, visits, segments, identity resolution, sync |
| `engagement` | Decision engine, campaigns, approvals, dispatch |
| `messaging` | WhatsApp and Instagram |
| `content` | Strategies, plans, photos, publishing |
| `advertising` | Meta ads, attribution |
| `intelligence` | Scoring, findings, questions |
| `ai` | One gateway for every model call |

Each owns its tables and exposes an interface. No module reaches into another's
data directly.

## Why not actual microservices

At one tenant, ~500 messages a month and one developer, eight independently
deployed services would add: eight pipelines, eight sets of secrets, network
calls where function calls would do, distributed tracing to debug what a stack
trace shows today, and eventual consistency between things that are currently
one transaction.

**That is cost with no corresponding benefit.** Nothing here needs independent
scaling. Nothing has a different availability requirement.

## Consequences

**Good.** Boundaries are enforceable by lint and review from day one. The
refactor is mechanical rather than architectural. Any module can be extracted
later — a well-bounded module is a service that has not moved yet.

**Bad.** "Microservices" is what was asked for, and this is not that. If the
requirement is organisational — separate teams owning separate deploys — this
decision does not meet it and should be revisited.

A module that is easy to extract is only easy if the boundary was respected.
Discipline is required with nothing structural forcing it.

**Revisit when:** one module genuinely needs different scaling or availability,
or separate teams need independent release cadence.

## Related

[TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md)

---

**Last verified:** 2026-09-01  
**Evidence:** `supabase/functions/mw-admin/index.ts` line count and action count, verified 2026-09-01.
