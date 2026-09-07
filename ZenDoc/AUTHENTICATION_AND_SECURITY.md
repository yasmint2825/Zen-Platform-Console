---
Last verified: 2026-09-07
Evidence source: authenticateUser, getUserTenantRole, userClient, and every requireOwner() call site in index.ts.
---

# Authentication and Security

[← Back to index](./README.md)

## User authentication

Standard Supabase Auth. Every request to `mw-admin` (except the narrow cron allow-list below) carries a `Bearer` JWT in the `Authorization` header. `authenticateUser(req)` (`index.ts:310`) validates it against Supabase Auth and returns `{userId, email}` or `null`. A `null` result is a hard 401 before any action logic runs.

## Tenant isolation — two real, independent layers

1. **Application-level role check.** `getUserTenantRole(userId, tenantId)` (`index.ts:318`) looks up `mw_tenant_users` for a role (`owner` or a lesser role — **[UNKNOWN — the full set of non-owner roles and what they're permitted was not exhaustively enumerated in this pass; `requireOwner()` gates are pervasive but the alternative role(s) allowed through non-owner-gated actions weren't cataloged]**). No role → 403.
2. **Row-Level Security, enforced by Postgres, not application code.** `userClient(req)` builds a Supabase client authenticated as the *calling user's own JWT* (not the service-role key) specifically for reads — so a bug in an application-level `.eq("tenant_id", ...)` filter cannot leak another tenant's data past RLS. Writes still go through the service-role `supabase` client, but only after the explicit role check above — this is genuine defense-in-depth, not a single point of failure.

## Cron / scheduled-job authentication

A separate, narrow mechanism for requests with no human session: a shared secret in the `x-cron-secret` header, checked against `CRON_SECRET` (env var), and only honored for a fixed, explicit allow-list of action names (`CRON_ACTIONS`, `index.ts:2322`): `send_due_scheduled`, `apply_ad_schedule`, `auto_reply_if_safe`, `generate_insights`, `label_outcomes`, `run_workflow`. An action not on this list cannot be reached via the cron secret even if someone obtained it — this was a deliberate design choice, not an oversight (per in-code comments explaining the narrowing).

## Credential storage

Third-party API tokens (WhatsApp, Instagram, Meta Ads, leads) are stored in `mw_tenant_credentials`, encrypted with AES-GCM using a key from `CREDENTIAL_ENCRYPTION_KEY` (`encryptSecret`/`decryptSecret`, `index.ts`). Lead-generation tokens are a documented exception, stored **unencrypted**, because the webhook that needs them runs without the encryption key available — a real, acknowledged tradeoff, not an inconsistency to "fix" without understanding why.

## AI auto-reply safety gating — the most consequential safety logic in the codebase

`handleAutoReply()` will not send a message unsupervised unless **all** of the following hold:
- Auto-reply is enabled for the tenant
- The message isn't a reaction or a bare acknowledgement ("ok", "thanks")
- The per-conversation auto-reply count hasn't exceeded the configured max
- The message doesn't match a hand-off pattern (complaint language, a request to change a booking, a request for a person, a care/medical need) — these always go to a human, some with an automatic "call us" deflection, complaints and care needs never deflected automatically
- The model's own `safe_to_send` flag is true, it didn't use a fact not marked safe-to-send, and its stated confidence meets the tenant's configured minimum

Anything that fails any of these checks is held for a human, logged with the specific reason, and (where appropriate) gets an automatic "let me check and get back to you" holding reply with the salon's phone number — never silence.

## Do-not-disturb / opt-out enforcement — closed as a real gap during development

Worth documenting precisely because it was a genuine, fixed defect: the do-not-disturb check used to only be enforced on the manual one-off send path (`send_one_off`). Every bulk/scheduled/automatic send path had no such check. This was fixed by moving the check into `approveAndSendDecision`, the one shared function every non-one-off send path funnels through — closing the gap for all of them at once rather than patching each path individually. Any new send path added in future **must** go through `approveAndSendDecision` or it will silently reintroduce this exact gap.

## What this document does not cover

- Database-level RLS policy definitions (they live in Supabase, not this repo) — **[UNKNOWN]**
- Non-owner role permissions, exhaustively — **[UNKNOWN, see above]**
- Rate limiting, if any exists at the Edge Function or API gateway level — **[UNKNOWN — not evidenced in index.ts itself]**
