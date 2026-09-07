---
Last verified: 2026-09-07
Evidence source: Every console.log/console.warn/console.error call, and the get_schedule_health action, in index.ts.
---

# Observability and Operations

[← Back to index](./README.md)

## Logging: `console.*` only, no structured logging or log aggregation evidenced

`console.error`, `console.warn`, and `console.log` calls exist throughout `index.ts` at meaningful failure points (e.g. a failed `my_tenants` read, a workflow dispatch failure, an LLM call logging failure). These land wherever Supabase Edge Function logs land by default — **[UNKNOWN — whether any log aggregation, alerting, or retention policy is configured beyond Supabase's own default log viewer]**.

## The one genuine, purpose-built health-check feature: `get_schedule_health`

This is worth calling out specifically because it's a real, thoughtful piece of operational tooling, not boilerplate — it exists because two real production incidents (a dispatcher silently returning 401 for a full day with nothing sending, and a sync silently dropping guest visits) were only caught by chance. It checks, per job, its own real evidence of having run (last agent run timestamp, most recent transaction imported, count of messages overdue past their scheduled slot, most recent inbound WhatsApp message, most recent prediction score, most recent daily-intelligence computation) and reports each as `ok`/`overdue`/`failed`/`unknown` against a per-job cadence, not one blanket threshold. This is the closest thing this codebase has to a health-check endpoint, and it's accessible only via the action API (`get_schedule_health`), not a dedicated `/health` route.

## Cost observability: real, and worth preserving in any migration

Every Claude API call is logged to `mw_llm_calls` (`callClaude()`, `logClaudeCall()`) with purpose, model, token counts (including cache read/write), duration, success, and computed cost — deliberately, because untracked LLM spend was a real concern during development ("token consumption looks heavy" could previously only be answered by reasoning about which cron jobs existed, not by looking at data). This is a genuinely valuable pattern worth carrying into the target architecture rather than treating as incidental.

## What's explicitly missing

- No dedicated error-tracking service integration (Sentry or equivalent) — **[UNKNOWN — not evidenced anywhere in the code]**
- No metrics/dashboarding beyond what the application itself queries and displays to the salon owner (which is business metrics, not system metrics)
- No alerting — `get_schedule_health` surfaces problems when queried, it does not push a notification anywhere
- No distributed tracing (unsurprising, given there's only one real service today)
