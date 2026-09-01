# Developer Onboarding

## Day 1 — Read

1. [SYSTEM_CONTEXT.md](SYSTEM_CONTEXT.md) — what this is
2. [CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md) — how it is built
3. [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](KNOWN_RISKS_AND_TECHNICAL_DEBT.md) — what will bite you

Then open `supabase/functions/mw-admin/index.ts` and read `handleAutoReply`. It
is the densest, most-corrected code in the project and the best introduction to
how the platform actually thinks.

## Access to request

- [ ] Supabase project — database, functions, secrets, logs
- [ ] GitHub repository — code and Actions
- [ ] Meta Business Manager — templates, ad account, webhooks
- [ ] Anthropic and Replicate consoles (keys are already set)

## Day 2 — Orient

```bash
# every action in mw-admin
grep -oE 'case "[a-z_]+"' supabase/functions/mw-admin/index.ts | sort -u

# check for duplicate definitions before you touch anything
grep -c 'case "plan_wave"' supabase/functions/mw-admin/index.ts

# where the platform stands right now
psql "$SUPABASE_DB_URL" -c "select status, count(*) from mw_agent_decisions
  where tenant_id='minicuts' group by 1;"
```

## Day 3 — First change

Pick something from the Medium list in
[KNOWN_RISKS_AND_TECHNICAL_DEBT.md](KNOWN_RISKS_AND_TECHNICAL_DEBT.md). Good
first tasks:

- Read the WhatsApp daily limit from Meta instead of the hardcoded 250
- Add a batch cap to the approve-all path
- Audit what queries `mw_predictions` and `mw_message_templates`

Follow [DEPLOYMENT_RUNBOOK.md](DEPLOYMENT_RUNBOOK.md). Deploy in the morning,
when you can watch it.

## The five rules

1. **Paginate every query** against a table that could grow. The 1,000-row cap is
   silent and has caused weeks of wrong campaigns.
2. **Never discard an error.** `const { data, error } = ...` and check it.
3. **Grep for the name before adding a function or a `case`.** Duplicates are
   invisible and the later one wins. Four incidents so far.
4. **Run `notify pgrst, 'reload schema';`** after any schema change.
5. **Both cron headers, every time** — `Authorization` and `x-cron-secret`.

## Working with others

**UNKNOWN:** no branching strategy, PR template, or review convention is
established. Agree one before a second developer starts. Suggested minimum:

- Branch per change, PR into `main`, one review
- Migrations numbered and never edited once run
- Deploys announced, because there is no staging to absorb a mistake

## Who to ask

The platform was built by the owner working with an AI assistant. There is no
other institutional memory. Where this documentation says **UNKNOWN**, nobody
currently knows — treat those as work items.

---

**Last verified:** 2026-09-01  
**Evidence:** Onboarding path derived from the codebase; conventions not yet established.
