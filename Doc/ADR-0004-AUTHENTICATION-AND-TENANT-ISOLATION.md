# ADR-0004: Authentication and Tenant Isolation

**Status:** Accepted — urgent
**Date:** 2026-09-01

## Context

**This is the most serious open issue in the platform.**

Row-level security is established on 2 tables of ~55: `mw_tenants` and
`mw_tenant_users`. Everything else is accessed with the service-role client,
which bypasses RLS entirely.

Isolation therefore depends on every query remembering `.eq("tenant_id", ...)`.
Across 221 actions, written over months, by one person.

At one tenant this is invisible — there is no other tenant's data to leak. At a
hundred, one omission exposes another salon's customer list.

## Decision

**Four independent layers. Any one will eventually be bypassed by someone in a
hurry; the point is that all four would have to fail together.**

### 1. RLS on every table
Postgres enforces isolation whatever the application forgets.

```sql
alter table <t> enable row level security;
create policy tenant_isolation on <t>
  using (tenant_id = current_setting('app.tenant_id', true));
```

### 2. Request-scoped tenant context
Set once from the JWT at the start of a request, never passed as a parameter a
developer could forget or get wrong.

### 3. Repository base class
Applies the tenant filter automatically. Raw queries lint-blocked, with an
explicit escape hatch that requires justification in review.

### 4. Automated isolation test per module
Log in as tenant A, assert tenant B is invisible. Runs on every commit.

**Layer 4 is what catches a failure. Layers 1–3 are what make it unlikely.**

## Authentication

Unchanged in the short term: Supabase Auth, JWT, `requireOwner()`.

Longer term, an enterprise buyer will require SSO, MFA and access audit. Auth0 or
Entra ID rather than building it. **Not urgent** — no enterprise buyer exists
yet, and the isolation work does.

## Sequencing

Before a second tenant is onboarded:

1. Enumerate every table and its current RLS state
2. Apply policies to all of them
3. Add the tenant context helper
4. Write one isolation test and make it fail correctly
5. Then the repository layer, as part of Phase 3

Steps 1–4 are days, not weeks, and are the highest-value work available.

## Consequences

**Good.** Isolation stops being a matter of discipline. A missing filter becomes
a query returning nothing rather than another tenant's data.

**Bad.** RLS costs query performance, more on complex joins. Service-role paths
must be audited individually — some legitimately need it, and each needs
justifying. Setting the tenant context correctly on every path is itself
something that can be got wrong.

**The cron paths are a specific risk:** they have no user session and therefore
no JWT to derive tenant context from. They will need an explicit, reviewed
mechanism.

## Related

[AUTHENTICATION_AND_SECURITY.md](../AUTHENTICATION_AND_SECURITY.md),
[KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md)

---

**Last verified:** 2026-09-01  
**Evidence:** RLS policies found in `supabase/*.sql`; service-role usage across `mw-admin`.
