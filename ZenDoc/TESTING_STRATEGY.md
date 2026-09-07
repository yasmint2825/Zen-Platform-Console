---
Last verified: 2026-09-07
Evidence source: Full file listing of the repository — no test files of any kind exist.
---

# Testing Strategy

[← Back to index](./README.md)

## What actually exists: no automated test suite

There are no `*.test.*`, `*.spec.*`, or any other test files anywhere in this repository. There is no test runner configured, no CI pipeline that would run one, and no coverage tooling. **This is a genuine, significant gap, not an oversight to soften in the retelling.**

## What existed instead, during development

Every change made to this codebase during development was verified through a manual but rigorous process, repeated for essentially every change:

1. **Static verification** — for the frontend, an HTML tag-balance check and a Node.js syntax check (`node --check`) run against the extracted `<script>` content before anything ships. For the backend, a TypeScript compile check (`tsc --noEmit --skipLibCheck`) with one known, accepted pre-existing error.
2. **Behavioral verification via headless browser automation** — Playwright driving a real headless Chromium instance against the actual `zen-clickable-prototype.html` file, with `fetch()` intercepted and mocked to return realistic backend responses, clicking through the actual user flow and asserting on real DOM state (not just "does it render without crashing"). Screenshots taken for visual confirmation before anything is presented as complete.
3. **No equivalent automated verification existed for the backend's actual business logic** — `index.ts` changes were verified by compilation success plus manual reasoning about the code, not by running the actions against a real or mocked Supabase instance. **This is the single biggest testing gap in the codebase.**

## What is explicitly not covered by anything

- No unit tests for any pure function in `index.ts` (currency formatting, mobile number normalization, the JSON-repair logic, etc. — several of these are non-trivial and would benefit most from unit coverage)
- No integration tests against a real or test Supabase database
- No test coverage of the AI-dependent paths (auto-reply safety gating, monthly strategy generation) beyond manual review of prompts
- No load/performance testing evidenced anywhere
- No test coverage of the webhook (`mw-whatsapp-webhook-index.ts`) at all

## Recommendation for the target architecture

This is a natural, low-risk place to introduce real automated testing as part of the migration rather than trying to retrofit tests onto the flat monolith first — see [MIGRATION_PLAN.md](./MIGRATION_PLAN.md). Extracting a service is a natural forcing function to also give it a real test suite, since a newly-drawn service boundary needs contract tests regardless.
