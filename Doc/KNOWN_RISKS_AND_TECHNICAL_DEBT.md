# Known Risks and Technical Debt

Ordered by consequence. Every entry is observed, not hypothetical.

## Critical

### Tenant isolation lives in application code
RLS is established on 2 tables of ~55. Everything else uses the service-role
client and depends on each query remembering `.eq("tenant_id", ...)`.
**One omission leaks another salon's customers, and nothing would catch it.**
Invisible at one tenant; the whole business at a hundred.

### One environment
No staging, no test project. Every change ships to the system serving real
customers. The only way to test is to deploy and watch.

### No tests, no CI
Nothing runs on commit. Regressions are found by users.

## High

### `mw-admin` is 11,810 lines with 221 actions
No module boundaries, no way to reason about blast radius, and cold starts cost
1–2 seconds. The most valuable refactor available and the riskiest.

### `console.html` is 644KB with no modules
A function defined twice silently uses the later definition. **Observed four
times:** `loadCommandCenter`, `oneOffModeChanged`, a 185-line duplicated block,
and a duplicate `plan_wave` case that disabled the wave planner entirely.

### No alerting
Failures are found by noticing an absence.

### Silent pagination
Supabase caps at 1,000 rows. The daily agent saw 1,000 of 3,585 profiles for an
unknown period; every campaign was wrong and nothing reported it. Mitigated by
`fetchAllPages`, but any new query can reintroduce it.

## Medium

| Debt | Consequence |
|---|---|
| ML tiers not joined to campaign targeting | The model's output cannot be acted on. Largest functional gap. |
| Approve-all has no batch cap | Processes a whole group in one invocation; observed dying at 546 and stranding 54 rows in `approved` that nothing retries |
| The 250/day WhatsApp limit is hardcoded | It is a tier that rises. Should be read from Meta. |
| `mw_predictions`, `mw_message_templates` queried but absent | Features silently return nothing |
| No retention on message tables | Unbounded growth |
| Instagram token expiry is silent | Publishing stops at 60 days with no warning |
| Canva is scaffolding | Looks connected; cannot create designs |
| No dead-letter queue on webhooks | A message lost after the 200 is lost silently |
| Incremental sync unscheduled | Today's visits invisible until tomorrow |

## Patterns behind most incidents

1. **Swallowed errors.** `const { data } = await supabase...` discards the
   reason; a failed read looks like an empty result.
2. **Name collisions in a file with no modules.**
3. **Facts left to be inferred.** Where a fact is knowable in code, state it —
   the reply assistant asked a returning customer about a first haircut because
   "has been in before" was left to be derived from a visit count.

## Deliberate decisions, not debt

| Choice | Why |
|---|---|
| Deterministic agent, no LLM | Model calls timed out on 3,500 customers, cost money for rules, and could not explain themselves |
| No semantic caching | At ~500 replies/month the embedding call costs more than it saves |
| Public storage buckets | Meta must fetch images by URL |
| Approval before sending | Messages to real customers are not reversible |

---

**Last verified:** 2026-09-01  
**Evidence:** Incidents observed during development 2026-08-25 to 2026-09-01; code inspection.
