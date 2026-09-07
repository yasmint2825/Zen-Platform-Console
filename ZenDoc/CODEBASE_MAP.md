---
Last verified: 2026-09-07
Evidence source: Directory listing of the three source files; no subdirectories exist in this repository as documented.
---

# Codebase Map

[← Back to index](./README.md)

There is no directory structure to speak of — three files at (or near) repository root:

```
.
├── index.ts                         # backend: Supabase Edge Function "mw-admin"
├── mw-whatsapp-webhook-index.ts     # backend: Supabase Edge Function "mw-whatsapp-webhook"
├── zen-clickable-prototype.html     # frontend: single-file SPA
└── (GitHub Actions workflow YAML files — not reviewed in this pass)
```

This flat layout is the single biggest reason a new developer needs [CURRENT_ARCHITECTURE.md](./CURRENT_ARCHITECTURE.md)'s internal-organization notes rather than being able to orient by folder names the way most projects allow.

## `index.ts` — reading order for a new developer

Don't read top to bottom. Instead:

1. Read `Deno.serve(async (req) => {...})` first (search for it) — this is the actual entry point and shows the full auth/routing shape in about 40 lines before the `switch` begins.
2. Pick one action you care about and search for `case "that_action_name"`. Each case is largely self-contained — most of the logic for a feature lives inside its own case block, not scattered across the file.
3. When a case calls a bare function name (not `call(...)`, not a `case`), that's one of the shared helpers defined earlier in the file (see the list in [CURRENT_ARCHITECTURE.md](./CURRENT_ARCHITECTURE.md)) — search for `function <name>` or `async function <name>`.

## `zen-clickable-prototype.html` — reading order for a new developer

1. `<style>` block first — all CSS is here, using a small set of CSS custom properties (`--green`, `--muted`, `--line`, etc.) and a consistent small component vocabulary (`.card`, `.mini-grid`, `.wiz-steps`, `.list-row`) reused across nearly every screen.
2. `function go(name)` (`zen-clickable-prototype.html:1392`) — the top-level page router. Each of the six sidebar pages (see [FUNCTIONAL_CAPABILITIES.md](./FUNCTIONAL_CAPABILITIES.md)) has a corresponding top-level render function.
3. `function call(action, args)` — the one function through which every single backend request is made. Worth reading once; every other function's backend interaction follows this exact shape.
4. `async function flow(fn)` and the `wizSteps()` helper — the pattern used for every multi-step wizard (campaign sending, monthly planning, single-post creation).

There are 212 top-level JS functions in this file (`grep -cE '^(async )?function [a-zA-Z]' zen-clickable-prototype.html`). Naming is generally `<page><Action>` (e.g. `campAudience`, `campMessage`, `contentBrief`, `contentGenerate`) — grep the page-name prefix to find everything belonging to one screen.

## `mw-whatsapp-webhook-index.ts`

Small (380 lines) and single-purpose. `Deno.serve` at line 80 is the entire entry point; almost everything before it is credential decryption and media re-hosting helpers.

## Naming conventions actually observed (not aspirational)

- Backend action names: `snake_case`, verb-first (`get_`, `list_`, `create_`, `save_`, `approve_`, `generate_`) — consistently applied across all 243 actions.
- Frontend functions: `camelCase`, page-prefixed for anything belonging to a specific screen.
- Database tables: `mw_` prefix for platform-owned tables (72 unique tables referenced — see [DATA_MODEL.md](./DATA_MODEL.md)); a handful of un-prefixed tables (`customers`, `assets`, `generations`, `content_plan_items`, `creative_briefs`, `brand_profiles`, `brand_rules`, `business_strategy`, `monthly_content_strategy`, `historical_transactions`) that predate the `mw_` convention or are shared with the separate Loyalty Passport app — **[UNKNOWN — the exact reason for the inconsistent prefix was not documented in the code and should be confirmed with whoever named these]**.
