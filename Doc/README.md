# Zen Platform — Documentation

Marketing and customer-retention platform for MiniCuts FZCO, a children's hair
salon in Dubai Silicon Oasis. Single tenant today; multi-tenant by construction.

This directory is the entry point for anyone joining the project. Read
[SYSTEM_CONTEXT.md](SYSTEM_CONTEXT.md) first, then
[DEVELOPER_ONBOARDING.md](DEVELOPER_ONBOARDING.md).

## Index

### Understand the system
| Document | Answers |
|---|---|
| [SYSTEM_CONTEXT.md](SYSTEM_CONTEXT.md) | What this is, who uses it, what it talks to |
| [FUNCTIONAL_CAPABILITIES.md](FUNCTIONAL_CAPABILITIES.md) | What it does, feature by feature |
| [CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md) | How it is built today |
| [CODEBASE_MAP.md](CODEBASE_MAP.md) | Where everything lives |

### Understand the data and interfaces
| Document | Answers |
|---|---|
| [DATA_MODEL.md](DATA_MODEL.md) | Tables, keys, ownership |
| [API_AND_INTEGRATIONS.md](API_AND_INTEGRATIONS.md) | The API surface and external systems |
| [AUTHENTICATION_AND_SECURITY.md](AUTHENTICATION_AND_SECURITY.md) | Who can do what, and how secrets are held |
| [JOBS_AND_SCHEDULES.md](JOBS_AND_SCHEDULES.md) | What runs unattended |

### Work on it
| Document | Answers |
|---|---|
| [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) | Getting it running |
| [DEPLOYMENT_RUNBOOK.md](DEPLOYMENT_RUNBOOK.md) | Shipping a change |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | How changes are verified today |
| [OBSERVABILITY_AND_OPERATIONS.md](OBSERVABILITY_AND_OPERATIONS.md) | Finding out what went wrong |
| [DEVELOPER_ONBOARDING.md](DEVELOPER_ONBOARDING.md) | First week |

### Where it is going
| Document | Answers |
|---|---|
| [KNOWN_RISKS_AND_TECHNICAL_DEBT.md](KNOWN_RISKS_AND_TECHNICAL_DEBT.md) | What is wrong and how badly |
| [TARGET_ARCHITECTURE_ALIGNMENT.md](TARGET_ARCHITECTURE_ALIGNMENT.md) | The SaaS target, and the distance to it |
| [MIGRATION_PLAN.md](MIGRATION_PLAN.md) | Phased path, without stopping the platform |
| [adr/README.md](adr/README.md) | Decisions and why |

## Conventions

- Every document carries a **Last verified** date and its evidence source.
- Anything not established from the code is marked **UNKNOWN** rather than guessed.
- File references are repository-relative, e.g. `supabase/functions/mw-admin/index.ts`.
- No secret values appear anywhere. Names only.

## A caution about this documentation

It was produced by reading the repository, not by interviewing the people who
built it. Where the code is ambiguous the ambiguity is recorded rather than
resolved. Treat **UNKNOWN** markers as work items, not as omissions.

---

**Last verified:** 2026-09-01
**Evidence:** Repository read at commit HEAD; see individual documents for specifics.
