---
Last verified: 2026-09-07
Evidence source: AUTHENTICATION_AND_SECURITY.md
---

# ADR-0004: Authentication and Tenant Isolation

[← Back to ADR index](./README.md)

**Status: Proposed**

## Context

Today, authentication and tenant isolation work as two real, independent layers within one process (see [AUTHENTICATION_AND_SECURITY.md](../AUTHENTICATION_AND_SECURITY.md)): a Supabase Auth JWT check, and Postgres RLS enforced via a per-request, user-scoped Supabase client for reads. This works because there is only one backend process making the database connection. A multi-service architecture breaks that assumption — each service will make its own database connections (or calls to other services), and the JWT needs to remain trustworthy across all of them.

## Decision (proposed)

1. **Keep Supabase Auth as the single identity provider** for the target architecture — no reason evidenced in the current codebase to replace it, and doing so would be a large, separately-justified decision on its own.
2. **Each service independently validates the incoming JWT** (as `authenticateUser()` does today) rather than trusting an upstream service's unchecked assertion of identity — this preserves the current "every request proves who it is" property rather than weakening it at a new internal boundary.
3. **RLS remains the tenant-isolation enforcement mechanism for any service that talks to the shared database directly**, using the same user-scoped-client pattern (`userClient()`) as today. Services that don't talk to the database directly (calling another service's API instead, per [ADR-0003](./ADR-0003-DATA-OWNERSHIP.md)) inherit tenant isolation from whichever service they call, and must forward the original user's JWT (or an equivalent, service-to-service-safe token) on that call — never re-authenticate as a generic service account that loses the original tenant context.
4. **Preserve the narrow cron-secret allow-list pattern** (`CRON_ACTIONS`, see [AUTHENTICATION_AND_SECURITY.md](../AUTHENTICATION_AND_SECURITY.md)) for any genuinely unattended, scheduled work in the target architecture — an explicit allow-list per action/endpoint, not a blanket bypass credential usable for anything.

## Alternatives considered

- **A dedicated internal API gateway that authenticates once and issues short-lived internal tokens to downstream services.** A reasonable, common pattern, and worth reconsidering once the service count grows — rejected as the *starting* decision because it's a new piece of infrastructure the current codebase gives no evidence of needing yet, and introducing it before Phase 1 of the migration adds risk to the very first extraction for a problem that doesn't exist until there are several services deep in a call chain.
- **Service-to-service calls authenticated by a shared secret (like the current cron-secret pattern) instead of forwarding the user's JWT.** Rejected for user-initiated request paths specifically, because it would silently lose the actual tenant/user context RLS depends on — a service receiving only "this came from Messaging Service" with no user identity cannot enforce RLS correctly. Appropriate to keep, narrowly, for genuinely unattended cron-style work only, matching current practice.

## Consequences

- Every service needs its own Supabase Auth validation logic (or a shared library implementing it identically) — a real piece of shared code to get right once and reuse, not reinvent per service.
- JWT forwarding across service-to-service calls needs to be a deliberate, checked part of every new internal API's design — the do-not-disturb enforcement gap documented in [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](../KNOWN_RISKS_AND_TECHNICAL_DEBT.md) (item 3) is a direct precedent for what happens when a "shared check" isn't actually enforced on every path; the same discipline applies here.
- Non-owner role permissions are currently **[UNKNOWN in full — see AUTHENTICATION_AND_SECURITY.md]**; this must be resolved before finalizing per-service authorization logic, since "owner" is the only role whose permissions are exhaustively evidenced today.
