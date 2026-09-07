---
Last verified: 2026-09-07
Evidence source: CRON_ACTIONS allow-list and every action referencing "scheduled"/"cron"/"dispatch" in index.ts.
---

# Jobs and Schedules

[← Back to index](./README.md)

## Confirmed scheduled work (via `x-cron-secret`, see [AUTHENTICATION_AND_SECURITY.md](./AUTHENTICATION_AND_SECURITY.md))

| Action | Purpose | Cadence | Evidence |
|---|---|---|---|
| `send_due_scheduled` | Dispatches WhatsApp sends whose `scheduled_send_at` has arrived, in batches of 25, oldest first | Every 5 minutes (per in-code comment) | `index.ts` |
| `apply_ad_schedule` | Applies hour/day/budget rules to Meta ad sets | Hourly (per in-code comment) | `runAdSchedule()` |
| `auto_reply_if_safe` | Called by the webhook per inbound message, not on a fixed schedule itself | Event-driven | `handleAutoReply()` |
| `generate_insights` | Daily AI-generated insight summary | **[UNKNOWN — cadence not stated in-code beyond "daily"; exact time not confirmed]** | `handleGenerateInsights()` |
| `label_outcomes` | Labels closed-window decisions with their real outcome (did the customer return) for future model training | **[UNKNOWN cadence — logic checks windows already closed, so likely daily]** | `index.ts` |
| `run_workflow` | Dispatches a named GitHub Actions workflow | Called by pg_cron per workflow, presumably | `index.ts` |

## GitHub Actions workflows dispatched (names only — contents not reviewed)

`daily_intelligence.yml`, `train_model.yml`, `generate_social_content.yml`, `cleanup_old_generations.yml`, `publish_scheduled_content.yml`, `metric_learnings.yml`

**[UNKNOWN — the actual pg_cron schedule definitions (which call `run_workflow` for which workflow, at what times) live in the Supabase project's cron configuration, not in this repository. This document cannot confirm exact cadence without access to that configuration directly.]**

## A confirmed historical gap worth knowing

Prior project notes describe GitHub's own native cron scheduling as having been unreliable in practice for this project (findings written at inconsistent times not matching the intended schedule), which is why scheduled dispatch moved to Supabase's `pg_cron` calling `mw-admin`'s `run_workflow` action instead of relying on GitHub Actions' own `schedule:` trigger. If extending this system, prefer the pg_cron → `run_workflow` pattern over adding a new native GitHub Actions schedule trigger, consistent with this precedent.

## Non-scheduled but still "background" — the dispatcher pattern

`send_due_scheduled`'s batching design (25 at a time, oldest first, reporting how many remain) exists specifically to avoid one Edge Function invocation exhausting its execution time/memory trying to send an entire backlog at once, and to avoid a WhatsApp number's quality rating being hurt by a burst of simultaneous template sends. Any new bulk-dispatch job added to this codebase should follow this same batching shape rather than looping unboundedly.
