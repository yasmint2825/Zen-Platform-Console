---
Last verified: 2026-09-07
Evidence source: The Deno.serve() handler and all external fetch() calls in index.ts.
---

# API and Integrations

[← Back to index](./README.md)

## The internal API is one endpoint, action-routed

There is no REST resource design. The entire backend surface is a single POST endpoint (the Edge Function URL for `mw-admin`) taking a JSON body of `{ action: string, tenant_id?: string, ...actionSpecificParams }`. Every one of the 243 actions is a string literal `case` in one `switch` statement. There is no OpenAPI spec, no route file, no per-resource controller — the `action` name **is** the API contract.

This has a direct, practical consequence for [TARGET_ARCHITECTURE_ALIGNMENT.md](./TARGET_ARCHITECTURE_ALIGNMENT.md): splitting this into microservices means partitioning 243 action names by concern, not extracting existing route groups, because no such grouping exists at the transport layer today — only in comments and physical proximity within the file.

## External integrations — all called directly, no SDKs

| Service | Called for | Auth mechanism | Evidence |
|---|---|---|---|
| Anthropic API | Every AI reasoning/generation task (auto-reply, insights, strategy proposals, image prompts, Q&A) | `x-api-key` header, `ANTHROPIC_API_KEY` env var | `callClaude()`, `index.ts` |
| Meta Graph API — WhatsApp | Sending templates/text/images, template listing, phone number registration | Bearer token, decrypted from `mw_tenant_credentials` (AES-GCM, `CREDENTIAL_ENCRYPTION_KEY` env var) | `sendWhatsappTemplate`, `sendWhatsappText` |
| Meta Graph API — Ads | Spend analysis, ad set/campaign management, Custom Audience creation | Bearer token, per-tenant via `resolveMetaAds()`, with a legacy function-secret fallback | `resolveMetaAds()`, `create_custom_audience_from_segment` |
| Meta Graph API — Instagram | Publishing images/stories, Business Discovery (competitor data) | Bearer token, `graph.instagram.com` for publishing specifically — confirmed via direct-login token testing during development, not the Page-linked approach | `publishImageToInstagram()` |
| Replicate API | Image generation (Flux models), video generation (Wan), text-to-speech (Kokoro), video/audio merging | Bearer token, `REPLICATE_API_TOKEN` env var | `run_generation`, `generate_video_scene_clip`, `generate_scene_voiceover` |
| GitHub API | Dispatching scheduled workflows | Bearer token, `GITHUB_TOKEN` env var, allow-listed workflow filenames only | `run_workflow` |

None of these integrations use an official SDK — every call is a raw `fetch()` against the provider's REST API. **[UNKNOWN — whether this was a deliberate choice (avoiding SDK bundle size in a Deno Edge Function) or simply how it evolved; worth confirming before a migration reintroduces SDKs.]**

## Webhook-received (inbound) integration

`mw-whatsapp-webhook-index.ts` is the only externally-facing webhook receiver — it accepts Meta's WhatsApp Business webhook payload (messages, delivery/read statuses) and is matched to a tenant by `phone_number_id` (a shared endpoint, multi-tenant by lookup, not by URL path).

## Internal service-to-service calls

The only service-to-service call in the system today: `mw-whatsapp-webhook` → `mw-admin` (action `auto_reply_if_safe`, authenticated via `x-cron-secret` since there is no end-user session in this context) and GitHub Actions workflows calling back into `mw-admin` for their actual work (exact callback actions per workflow are **[UNKNOWN — not reviewed, workflow YAML not included in this documentation pass]**).
