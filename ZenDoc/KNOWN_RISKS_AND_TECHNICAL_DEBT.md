---
Last verified: 2026-09-07
Evidence source: Direct code inspection across the full development history of this codebase; each item below is a confirmed finding, not a guess.
---

# Known Risks and Technical Debt

[← Back to index](./README.md)

This is the single most important document for migration planning ([MIGRATION_PLAN.md](./MIGRATION_PLAN.md), [TARGET_ARCHITECTURE_ALIGNMENT.md](./TARGET_ARCHITECTURE_ALIGNMENT.md)). Every item below is a confirmed finding from direct code inspection, not speculation.

## High severity

**1. Zero automated test coverage.** See [TESTING_STRATEGY.md](./TESTING_STRATEGY.md). A 13,400-line backend with 243 actions and no unit or integration tests is the single largest risk to any confident refactor or extraction.

**2. No database migration files.** Every schema change was a standalone SQL snippet run manually in the Supabase SQL Editor, never committed to version control. There is no way to reconstruct the current schema's history, no way to safely replay it against a fresh environment, and no way to know with certainty which snippets have actually been run against production. This is a blocking concern for setting up any second environment (staging, or a new microservice's own database).

**3. Frontend/backend deployment drift is a proven, repeated failure mode.** The frontend (a static file) and backend (requiring an explicit CLI deploy) have gone out of sync multiple times during development, each time producing a confusing "the fix isn't working" report that was actually a stale deployment, not a code defect. Any CI/CD introduced for the target architecture must treat this as a design constraint, not an incidental improvement.

**4. Marketing hub's "Recently created" list is mock data.** `DATA.posts` — a static, hardcoded array — not real content. `contentDetail()` was patched to fail honestly rather than show broken output when reached from this list, but the list itself was not rebuilt as of this documentation pass. **[UNKNOWN — may have been addressed since; confirm against current `zen-clickable-prototype.html`.]**

## Medium severity

**5. `index.ts` is a single 13,400-line file with no internal module boundaries.** Every one of the 243 actions lives in one `switch` statement in one file. This is the direct, primary reason a genuine microservice migration is a significant undertaking rather than a mechanical refactor — there is no existing seam to split along; boundaries have to be actively designed (see [ADR-0002](./adr/ADR-0002-SERVICE-BOUNDARIES.md)).

**6. Inconsistent table naming.** Most platform tables use an `mw_` prefix; a meaningful minority (`customers`, `assets`, `generations`, `content_plan_items`, `creative_briefs`, `brand_profiles`, `brand_rules`, `business_strategy`, `monthly_content_strategy`, `historical_transactions`) do not. The reason wasn't documented in-code. Worth resolving *before* deciding data ownership per service ([ADR-0003](./adr/ADR-0003-DATA-OWNERSHIP.md)), since un-prefixed tables are exactly the kind of thing that gets silently assumed to belong to "whichever service touches it most," which may be the wrong assumption.

**7. Two credential-encryption postures coexist by design, not oversight.** Most third-party tokens are AES-GCM encrypted; lead-generation tokens are stored unencrypted specifically because the webhook consuming them runs without the encryption key available. This is a real, documented tradeoff in the current architecture, not something to "fix" without first solving the underlying key-distribution problem in the target architecture.

**8. Meta Strategy Library (Custom Audience creation) stops short of a complete workflow.** It creates real, working Meta Custom Audiences from real customer data, but building the actual ad set and creative around that audience is still a manual step in Meta Ads Manager. Presented honestly as Phase 1 in the product itself — worth knowing this boundary exists before assuming the ad-creation pipeline is further along than it is.

**9. Canva integration is explicitly unfinished scaffolding.** The connection/OAuth flow exists and is real, but the actual design-creation and export endpoints were never verified against Canva's Connect API — marked directly in the code as untested, with next steps listed. Don't build on top of this assuming it works end-to-end.

## Lower severity, still worth tracking

**10. No environment separation evidenced.** Only one Supabase project ID appears anywhere in the codebase or prior project context. If a staging environment exists, it isn't referenced in code.

**11. No rollback procedure documented for Edge Function deployments.**

**12. No error-tracking/alerting service integrated** — failures surface in Supabase's default log viewer and in `get_schedule_health`'s on-demand check, not proactively.

**13. Ad targeting hypotheses need real validation, not assumption.** The High-Value Customer Hunter strategy (top 25% of customers by spend) is explicitly documented in its own UI as "a hypothesis to test... not a settled fact" — this pattern (data-derived segment ≠ proven-effective segment) should be treated as a standing principle for any future targeting feature, not just this one.
