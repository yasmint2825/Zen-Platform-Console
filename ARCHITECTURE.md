# Zen Platform — Architecture Documentation

_Living document. Updated incrementally as the platform evolves — not a point-in-time snapshot. Last major update: ML infrastructure (prompt templates, semantic layer, dynamic SQL, analytics snapshot)._

## 1. What this is

A multi-tenant customer engagement SaaS platform, built starting from MiniCuts FZCO (a children's hair salon in Dubai Silicon Oasis) as tenant #1. The platform runs automated WhatsApp campaigns, a return-probability ML model, and a natural-language "ask a question" analytics layer — all designed to generalize to future tenants, not hardcoded to MiniCuts specifically (with a few explicitly-noted exceptions).

## 2. Repositories

- **MiniCuts app** — the salon's own operational staff app (`index.html` live, `index_whatsapp.html` test/staging). Manages customers, stamps, loyalty redemptions, Welcome Rewards.
- **Zen-Platform-Console** — the platform's own admin console (`console.html`), plus `ml_pipeline/` (Python training) and `.github/workflows/` (scheduled training).

## 3. Supabase project

Project ref: `wtapyfgtwkjyjrjdnhkb`. One Postgres database, RLS enabled on every tenant-scoped table, policies keyed off `mw_is_tenant_member(tenant_id)`.

### Core platform tables
- `mw_tenants` — tenant registry (`loyalty_program_days` for expiry calc)
- `mw_tenant_users`, `mw_tenant_invites`, `mw_tenant_api_keys` — membership and API access
- `mw_tenant_credentials` — WhatsApp tokens, AES-GCM encrypted at rest
- `mw_template_map` — campaign `type_key` → Meta-approved WhatsApp template name

### Data layer
- `mw_transactions` — the canonical visit/sale record. Key columns: `customer_key` (real identity — see §5), `customer_mobile` (contact, not identity), `customer_name`, `transaction_date`, `amount`, `description`, `external_id` (dedup key), `source_type` (`excel_upload` | `scheduled_sync` | `api_push`)
- `mw_customer_profile` — birthday/segment, keyed by `customer_key`
- `mw_upload_batches` — upload audit trail

### Agent / campaign layer
- `mw_campaign_strategy` — per-campaign config: `enabled`, `offer_text`, `min_cooldown_days`, `threshold_value`/`threshold_value_max` (day windows), `segment_field`/`segment_overrides`, `applies_at_visit_counts`, `discount_percent`
- `mw_blackout_periods`, `mw_agent_decisions`, `mw_agent_runs`, `mw_strategy_audit_log`

### ML layer
- `mw_ml_models` — versioned logistic regression coefficients (feature names, weights, bias, scaler mean/std, validation metrics)
- `mw_customer_predictions` — precomputed return-probability per `customer_key`, refreshed every training run
- `mw_load_forecast` — weekly visit-load pattern (day-of-week averages, not individual date predictions — see §7)

### AI infrastructure layer (added most recently)
- `mw_prompt_templates` — system prompt CONTENT, separated from code. `{{placeholder}}` substitution at call time. Tenant override or platform default.
- `mw_metrics` — the semantic layer: named, pre-tested metric definitions (`active_customers_30d`, `lapsed_customers_90d`, `total_revenue`, `avg_visit_gap_days`)
- `mw_analytics_snapshot` — precomputed metric values (the "mini read replica"), refreshed every training run, keyed by `(tenant_id, metric_key, segment)` — `segment='all'` sentinel, never NULL (primary key columns can't be null)
- `mw_query_audit_log` — every dynamically-generated SQL query logged, whether it ran or was rejected

### Key Postgres functions
- `mw_run_readonly_query(query_text)` — `SECURITY INVOKER`, runs Claude-generated SQL through the CALLER's own RLS-scoped session. This is the actual safety mechanism for dynamic SQL — not trusting the generated query to be well-behaved, but letting the database itself enforce tenant isolation regardless of what the query does or doesn't filter on. Validates SELECT-only, no dangerous keywords, single statement, 5s timeout, 500-row cap.
- `mw_estimate_query_rows(query_text)` — runs `EXPLAIN` before execution, rejects anything estimated over 50,000 rows

## 4. Edge functions (Supabase)

| Function | Purpose | Auth |
|---|---|---|
| `mw-admin` | Console backend: campaign config, team/API keys, Ask a question, Generate insights | User session (RLS) + service-role for admin ops |
| `mw-ingest` | Excel/CSV and API-push data ingestion, computes `customer_key` | Tenant API key or user session |
| `mw-daily-agent` | SCAN → DECIDE → ACT engagement agent, generic across campaign types | Cron secret or manual (user session) |
| `mw-sync-minicuts` | Pulls MiniCuts' own `customers` table into the platform's `mw_transactions`/`mw_customer_profile` | Cron secret or manual |
| `mw-ml` | Pure read-only serving of precomputed ML results (model status, predictions, at-risk actions, load forecast) — **never trains anything itself** | User session |
| `send-whatsapp`, `whatsapp-config`, `whatsapp-templates`, `whatsapp-webhook` | WhatsApp Cloud API integration | Various |

**Deliberate separation**: training (Python, scheduled, GitHub Actions) vs. serving (TypeScript, on-demand, edge functions) are different jobs with different needs — conflating them is how "the model" quietly becomes untestable.

## 5. Customer identity — the sibling problem and its fix

**Original bug**: `customer_mobile` (phone number) was used as both identity AND contact method. Since multiple children can share one parent's phone (a real, common case for a kids' salon), this silently merged siblings' visit histories, stamp counts, and birthdays into one "customer."

**Fix**: `customer_key` = normalized `phone|name` (lowercase, trimmed) is now the real identity used for grouping, ML training, and campaign targeting everywhere. `customer_mobile` remains stored but is used ONLY for message delivery. Verified with a deliberate sibling test case (two people sharing one phone) scoring independently.

**Known tradeoff**: if a customer's name is later corrected (a typo fixed), they become a new identity going forward — acceptable given names are set once at registration in this business's actual workflow.

## 6. ML pipeline (`ml_pipeline/train_and_score.py`)

Real, tested, full-cycle ML — pandas + scikit-learn, not a hand-rolled shortcut. Runs via GitHub Actions on a schedule (weekly), connecting directly to Postgres via `DATABASE_URL` (bypasses RLS — treat like the service-role key).

- **Features** (5): `days_since_previous_visit`, `visit_number`, `days_since_first_visit`, `is_girl_segment`, `avg_spend`
- **Label**: did the customer return within 90 days of a given visit — only computed for visits old enough that the true outcome is actually known (no guessing at unresolved outcomes)
- **Model**: `LogisticRegression`, standardized features, genuine held-out validation split (never validates on training data)
- **Also computes**: weekly load forecast (day-of-week averages, all-time vs. recent-8-week), analytics snapshot (the 4 semantic-layer metrics, precomputed)

## 7. Honest limitations, stated on purpose

- **Load forecast is a weekly pattern, not date-specific predictions** — ~15 months of history is enough for "what's a typical Monday" (60+ repetitions) but not enough for real yearly seasonality (one Ramadan, one December).
- **Dynamic SQL fallback (`run_sql_query`) is capped at ~50,000 estimated rows** — a real capability limit, not just a speed optimization, favoring database stability.
- **The semantic layer only covers 4 metrics today** — everything else goes through the (slower, but fully capable) dynamic SQL path. Adding a 5th metric is an optional speed/consistency upgrade, never a prerequisite for answering a new question.
- **`mw_customer_profile` segment data has a residual ~6% "empty string" gap** from source data that wasn't cleanly "Male"/"Female" in the original export — not urgent, doesn't break anything, just incomplete for those specific customers.

## 8. Real bugs found and fixed (worth remembering why)

- **Partial unique index broke `ON CONFLICT` upserts** — Postgres can't use a partial index as a conflict target through a plain column-list upsert. Fixed with a full unique constraint.
- **Unpaginated queries silently truncated at 1,000 rows** (Supabase/PostgREST default) — caused wildly wrong counts in "Ask a question" until `fetchAllPages` was added, then made concurrent for performance.
- **Missing `external_id` mapping field in the Excel upload UI** — despite documentation claiming it worked, the console never actually sent it, so historical re-uploads were creating duplicates instead of updating in place.
- **`mw_customer_predictions` was keyed by phone, not `customer_key`** — reintroduced the sibling-merging bug in ML predictions specifically, even after fixing it everywhere else.

## 9. What's next (not yet built)

- Real-time push from MiniCuts' own app to `mw_transactions` (currently relies on scheduled sync + manual uploads)
- Monthly load forecast with year-over-year comparison where data supports it
- Additional ML features (service type, day-of-week, visit-gap trend)
- Expanding the semantic layer as common questions emerge
