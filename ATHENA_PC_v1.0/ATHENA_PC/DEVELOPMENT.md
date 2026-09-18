# ATHENA PC development notes

## Implementation

Python 3.10+ standard library, SQLite, plain HTML/CSS/JavaScript modules.
No package manager, external UI asset, CDN, telemetry, AI API, or hosted service is required.
The only network listener binds to 127.0.0.1. Never expose this server to the internet.

| Module | Responsibility |
|---|---|
| run.py | Windows-compatible startup, data directory, one-process lock, browser launch |
| athena/db.py | Schema v4, backed-up v1/v2/v3 migration, connection policy, transaction boundaries, reusable sale read model |
| athena/orders.py | Manual order inbox, order snapshots, status changes, audit history; no ledger effects |
| athena/validation.py | Input ranges, dates, text, existing references, movement totals |
| athena/catalog.py | Products, customers, receipts, stock corrections, archiving, settings |
| athena/ledger.py | Atomic sales, oldest-first receipts, returns, refunds, receipt corrections |
| athena/reports.py | Read models, dashboard, customer ledger, CSV escaping |
| athena/backup.py | SQLite online backups and schema-checked restoration into a fresh DB |
| athena/trash.py | Reversible grouped deletion, restore validation, and trash lifecycle |
| athena/editing.py | Audited corrections for sales, receipts, returns, and manual stock movements |
| athena/server.py | Loopback HTTP, session cookies, CSRF, idempotent mutation dispatch |
| athena/demo.py | Explicitly separate fictional demo seed |
| ui/app.js | Navigation, dashboard, tables, filters, pagination |
| ui/forms.js | Input dialogs, detail views, statement and restore flows |
| ui/orders.js | Order list/search/status filter/pagination, order forms and detail dialogs |
| ui/shared.js | Formatting, escaping, icons, request error handling |
| ui/statement.js | Printable current settlement statement with original line snapshots |

## Data invariants

- Amounts and quantities are bounded integers; no floating-point money arithmetic.
- Stock is the sum of movements, not an independently editable quantity column.
- Sale amount and original descriptions are immutable snapshots.
- Each return line references its original sale line, uses its price, and cannot exceed the unreturned quantity.
- Receivables = original amounts − returns − signed receipts. Opening balances are excluded from sales metrics.
- Negative receipts represent confirmed refunds or explicit receipt corrections.
- All mutations execute in BEGIN IMMEDIATE transactions with foreign-key enforcement and FULL synchronous mode.
- A process lock prevents two application servers from mutating the same DB independently.
- Each mutation carries a UUID and expected revision. Duplicate delivery returns the committed result; stale revisions are rejected.
- Reads and writes are serialized at application level; this intentionally favors simplicity for a small local office.
- User-facing deletion is a reversible soft-delete group. Sale deletion groups its lines, movements, receipts, returns and refunds; restore revalidates stock and balances.
- Purging removes recovery access but retains internal tombstones and audit history. Archival remains available for normal catalog lifecycle management.
- Saved-record edits write complete before/after JSON snapshots to `edit_history`; derived stock, receipts and balances are revalidated in the same transaction.
- Schema version is explicit; an unknown DB is never silently migrated or reset.

## Local security boundary

Host header must match the bound IPv4 loopback address and port. Authenticated session cookies are HttpOnly/SameSite=Strict.
Write requests require the matching Origin and a per-launch CSRF value. Cross-site fetch requests are rejected.
Static paths are allowlisted; database files and arbitrary filesystem paths cannot be served.
There are no user accounts, row-level permissions, or encryption at rest. Users with access to the local account/files remain trusted.
The launcher session token is stored in the local instance metadata solely to reopen an existing session and is never logged.

Backups are copies produced by SQLite's backup API. Restore first compares schema definitions, copies records into a fresh trusted schema,
validates relational/stock/sale/return/payment invariants, preserves a before-restore snapshot, and uses an atomic SQLite backup replacement.
Backup uploads cannot introduce SQL views, triggers, or executable schema extensions.

## Extension boundaries

Add future order/import/automation functionality as new domain operations using the existing transactional API.
Keep event detection separate from ledger mutation. External messages must not directly update derived stock or balances.
Do not use this local HTTP server as a public hosting architecture; authentication and deployment requirements need a separate design.
Before any schema change, add an explicit migration with a pre-migration backup and a version compatibility decision.

## Sources consulted

- [Python sqlite3 documentation](https://docs.python.org/3/library/sqlite3.html): parameterized statements, explicit transactions and the backup API.
- [Python http.server documentation](https://docs.python.org/3/library/http.server.html): local handler/server behavior; this implementation is not an internet production server.

See TEST_REPORT.md for what was and was not verified in the build environment.
