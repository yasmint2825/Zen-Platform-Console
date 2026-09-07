---
Last verified: 2026-09-07
Evidence source: The in-code deploy comment (index.ts:7), and every Deno.env.get() call across both Edge Functions.
---

# Local Development

[← Back to index](./README.md)

## Prerequisites

- Supabase CLI (for local Edge Function development/deployment) — **[UNKNOWN — exact required version not specified anywhere in the repo]**
- Deno (the Edge Functions runtime) — **[UNKNOWN — exact required version not specified]**
- No Node.js toolchain, no `package.json`, no npm/yarn — confirmed absent; this is not a Node project
- A modern browser for the frontend — no build step, `zen-clickable-prototype.html` is opened/served directly

## Environment variables required by `index.ts` (confirmed via `Deno.env.get()` calls)

| Variable | Used for |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role client (writes, and internal service-to-service calls) |
| `SUPABASE_ANON_KEY` | Anonymous client used inside `authenticateUser()` |
| `ANTHROPIC_API_KEY` | All Claude API calls |
| `REPLICATE_API_TOKEN` | Image/video/TTS generation |
| `CREDENTIAL_ENCRYPTION_KEY` | AES-GCM key for encrypting stored third-party tokens |
| `CRON_SECRET` | Shared secret for the cron-authenticated action allow-list |
| `GITHUB_TOKEN` | Dispatching GitHub Actions workflows |
| `META_ADS_ACCESS_TOKEN` | Legacy fallback for Meta Ads (per-tenant credentials are preferred; see `resolveMetaAds()`) |
| `CANVA_CLIENT_ID` / `CANVA_CLIENT_SECRET` | Canva integration — **note: this integration is explicitly marked as unfinished scaffolding in the code itself** (see [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](./KNOWN_RISKS_AND_TECHNICAL_DEBT.md)) |
| `ADSPIRER_API_KEY` | A connection test action only (`test_adspirer_connection`) — **[UNKNOWN — the broader scope of this integration wasn't evidenced beyond this one action]** |

No `.env.example` file exists in this repository. **[UNKNOWN — where the real values for these are actually sourced/stored for local development; likely Supabase project secrets, not a local file, but this should be confirmed with the team rather than assumed.]**

## Running the backend locally

**[UNKNOWN — no local-serve instructions are documented anywhere in this repository.]** The one command actually given, anywhere in the code, is the deploy command:

```
supabase functions deploy mw-admin --no-verify-jwt
```

Standard Supabase CLI local development would suggest `supabase functions serve mw-admin --env-file <path>`, but this is **not confirmed** against this specific project's setup — treat it as a reasonable starting guess, not a verified instruction, until confirmed.

## Running the frontend locally

No build step. Confirmed by direct inspection: `zen-clickable-prototype.html` is a complete, self-contained file. Opening it directly in a browser (`file://` URL) or serving it with any static file server should work — **[UNKNOWN whether CORS or other browser restrictions on `file://` origins cause any real friction; not tested as part of this documentation pass]**. During development, this file was tested extensively using headless Chromium via Playwright with mocked `fetch()` responses for the backend, which is a reasonable local testing pattern to continue.

## Deploying the webhook

No explicit deploy comment exists in `mw-whatsapp-webhook-index.ts` itself — by convention with `mw-admin`, this is almost certainly:
```
supabase functions deploy mw-whatsapp-webhook
```
**[UNKNOWN — unverified; confirm the exact function name registered in the Supabase project before relying on this command.]**
