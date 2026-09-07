---
Last verified: 2026-09-07
Evidence source: TARGET_ARCHITECTURE_ALIGNMENT.md, itself grounded in the 243 real actions catalogued from index.ts
---

# ADR-0002: Service Boundaries

[← Back to ADR index](./README.md)

**Status: Proposed**

## Context

`index.ts` implements 243 distinct actions in one file with no internal module boundary of any kind (see [CURRENT_ARCHITECTURE.md](../CURRENT_ARCHITECTURE.md)). [TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md) proposes six clusters based on evidence of how actions actually group by shared dependency (shared helper functions, shared table access, shared external API credentials).

## Decision (proposed)

Adopt the six-service boundary proposed in [TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md): **Messaging, Campaign, Customer Intelligence, Content, Ads, and a shared Platform layer** (tenant/auth, billing/model routing) — extracted in the order given in [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) (Ads and Content first, high-confidence boundaries; Messaging/Campaign/Customer Intelligence together and last, lower-confidence boundary requiring more care).

Explicitly **do not** attempt to decide the Messaging/Campaign/Customer Intelligence internal split now. [TARGET_ARCHITECTURE_ALIGNMENT.md](../TARGET_ARCHITECTURE_ALIGNMENT.md) rates this cluster "Medium confidence" specifically because the AI auto-reply engine alone reads across all three simultaneously to build one prompt — treat this as an open question to resolve with real data from Phase 1-2 of the migration, not a gap to paper over with a boundary chosen today.

## Alternatives considered

- **One boundary per current sidebar page** (Home, Campaigns, ZenWhatsApp, Marketing, Insights, Settings — see [FUNCTIONAL_CAPABILITIES.md](../FUNCTIONAL_CAPABILITIES.md)). Rejected: this is a *frontend navigation* structure, not evidence of backend coupling — several pages' actions read the same underlying tables and share the same helper functions, so mirroring the nav structure would recreate the current tight coupling behind six new network boundaries instead of removing it.
- **One boundary per database table group.** Rejected as too granular — would produce dozens of tiny services, most of which would need to call each other constantly for anything a single user action does today (e.g. approving a campaign decision touches `mw_agent_decisions`, `whatsapp_messages`, and `mw_customer_profile` in one operation).
- **A single "backend service" with internal module boundaries but one deployment unit.** A reasonable intermediate step, and arguably where Phase 0-1 of [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) effectively lands before full service extraction — but rejected as the *final* target, since it doesn't achieve the stated objective of independent deployability and independent developer ownership per service.

## Consequences

- Ads and Content extract with comparatively low coupling risk, based on real evidence (both already funnel through a small number of shared functions — `resolveMetaAds()` for Ads, `compilePromptForBrief()`/`callClaude()` for Content — that can become that service's own internal concern).
- The Messaging/Campaign/Customer Intelligence split will require either an internal API providing cross-domain read access (e.g. Messaging calling Customer Intelligence for auto-reply context) or an accepted architectural cost of that cluster staying more tightly coupled than the others for longer. This tradeoff is not resolved by this ADR and needs its own decision once Phase 1-2 provide real operating experience.
- The Platform layer (auth, tenant resolution, billing/cost tracking) becomes a hard dependency for every other service from day one — see [ADR-0004](./ADR-0004-AUTHENTICATION-AND-TENANT-ISOLATION.md) for how this should work across service boundaries.
