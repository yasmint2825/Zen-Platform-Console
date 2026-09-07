---
Last verified: 2026-09-07
Evidence source: zen-clickable-prototype.html sidebar navigation (lines 544-549) and the backend action each page's screens call.
---

# Functional Capabilities

[← Back to index](./README.md)

The frontend has exactly six top-level pages, defined in the sidebar nav (`zen-clickable-prototype.html:544-549`). Everything the product does lives under one of these six.

## 1. Home (`go('home')`)
- Daily "needs your attention" summary, sourced from `get_command_center_data`
- Month-to-date and quarter-to-date revenue, compared against the same period last month/quarter/last year (`get_daily_metric`, `get_quarter_comparison`)
- Quick-ask box that routes free-text questions to the AI Q&A pipeline (`ask_question`, see [API_AND_INTEGRATIONS.md](./API_AND_INTEGRATIONS.md))

## 2. Campaigns
- Per-category WhatsApp campaign management: nudge, lapsed (win-back), birthday, after-service, expiry, ready, new-customer-offer (`CAMPAIGN_KEYS`, `index.ts`)
- A wave-based manual send wizard: audience selection with tier/probability filtering → real approved-template preview with live variable inputs → send now or schedule for a real future time → holdout group automatically withheld for measurement (`plan_wave` / `commit_wave`)
- Pending review queue, bucketed by status (pending, rejected, holdout, sent, scheduled) — `get_decision_buckets`
- Do-not-disturb / opted-out customer management, reachable from WhatsApp settings

## 3. ZenWhatsApp
- Live conversation view with a real, timestamped message thread per customer
- AI auto-reply pipeline, grounded only in the salon's own price list and business facts, with an explicit safety gate before anything sends unsupervised (`handleAutoReply` / `auto_reply_if_safe`, see [AUTHENTICATION_AND_SECURITY.md](./AUTHENTICATION_AND_SECURITY.md) for the safety rules)
- Manual reply, including image sending
- WhatsApp settings: business facts, package priority, template mappings, do-not-disturb list, campaign settings

## 4. Marketing
- Monthly strategy generation: real business data + persistent business strategy + owner's stated priorities → an AI-proposed campaign theme, targeting, content pillars, and product focus (`propose_monthly_strategy`)
- Content plan generation against an approved strategy — real images via Replicate, real videos scene-by-scene, real captions (`generate_content_plan` and the `generate_video_scene_*` family)
- A quick, single-post flow ("Make a poster") using the same real generation pipeline (`generate_creative_brief` → `compile_prompt` → `run_generation`) with Zeely-style pre-filled-but-editable targeting drawn from the current approved strategy
- Meta Strategy Library: real Meta Custom Audiences built from actual customer segments (lapsed, high-value, birthday-soon) — `create_custom_audience_from_segment`. **This stops at audience creation**; ad set and creative construction around the audience is still manual, in Meta Ads Manager.
- Ad spend analysis, day/hour performance, creative fatigue detection, and an autopilot-style recommendation engine with explicit apply/reject per recommendation (`analyse_ad_spend`, `recommend_ad_actions`, `get_ad_table`)
- Competitor research via web search (`research_competitor`)
- Brand & Strategy: brand settings (colors, logo, default image model, voice), business strategy (frozen/read-only once filled, with an explicit Edit action), Brand DNA (AI-proposed brand rules, approved once, then applied to every generation)

## 5. Insights
- "Sales and Operations" — revenue, demographics, acquisition source, location breakdown, daily wait-time operations, all computed from real transaction data with explicit pagination past Supabase's ~1000-row default cap
- WhatsApp insights — delivery/read funnel, per-campaign holdout lift comparison, conversion-to-revenue attribution
- Customer lookup, individual customer profile and campaign history
- "What Zen is learning" — unsupervised metric associations surfaced from `mw_metric_learnings`

## 6. Settings
- Team/role management, API keys
- WhatsApp connection (phone number registration, template listing, test sending)
- Instagram, Meta Ads, and Lead Ads connections
- Do-not-disturb management (also reachable from WhatsApp settings)
- Billing / model selection — which Claude model each AI job uses, with real per-job cost visibility from `mw_llm_calls`

## Explicitly not built, or built but disconnected — do not assume otherwise

See [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](./KNOWN_RISKS_AND_TECHNICAL_DEBT.md) for the full, evidenced list. The two most consequential for anyone extending this codebase:
- The Marketing hub's "Recently created" post list runs on static mock data (`DATA.posts`), not real content — **[UNKNOWN whether this has since been connected; confirm against current `zen-clickable-prototype.html` before relying on this list]**.
- Video and Carousel formats are not available as a quick single-post flow — only as part of a full monthly content plan.
