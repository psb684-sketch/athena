# ATHENA PC 1.0 — verification record

Latest verification environment: Windows, Python 3.14, Node.js syntax checking.
The intended user environment is Windows with Python 3.10+ and Edge/Chrome.

## Passed: 21 automated business and security tests

Command: `python -m unittest discover -s tests -v`

1. Backdated receipts do not settle later invoices.
2. Backup round trip and reopened database preserve all checked sale details.
3. Invalid data, non-SQLite input, and modified schema do not overwrite live data.
4. Catalog/customer edits preserve original sale descriptions and prices.
5. Concurrent writes are serialized; a stale second sale cannot oversell.
6. CSV export escapes formula-like text and retains Korean UTF-8 text.
7. Duplicate product lines, negative/zero/fractional/boolean quantities are rejected.
8. Repeated request IDs cannot duplicate a committed sale; stale views are rejected.
9. Insufficient stock rolls back the entire sale including payments and revision.
10. Unauthenticated, foreign-Host, cross-site and missing-CSRF requests are rejected; arbitrary files are not served.
11. Opening debt is excluded from new revenue; receipts settle oldest debt first.
12. Receipt correction leaves the original and counter-entry, and rejects repeat correction.
13. Returns cannot exceed the remaining sold quantity; returned archived stock becomes active again.
14. Sale → partial receipt → partial return → confirmed refund preserves stock, balances and cash totals.
15. Stock correction requires a reason and leaves an exact movement entry.
16. Whole-sale deletion reverses linked stock, receipts and returns; trash restore reproduces the original sale detail.
17. Return deletion and restore include the automatically linked refund and inventory movement.
18. Unsafe stock deletion rolls back, while purged trash cannot be restored.
19. Schema v1 upgrades preserve live data and create a pre-migration backup before adding trash and edit-history tables.
20. Sale edits recalculate inventory and receivables, reject totals below receipts, and preserve before/after history.
21. Receipt, return and stock-movement edits recalculate refunds, balances and inventory atomically.

## Passed: actual launcher and HTTP integration

Command: `python tests/check_http_flow.py`

The check starts `run.py` as a real subprocess with a temporary empty database, opens its session through HTTP,
and exercises the application's real endpoints. It does not mock the application service or database.

- Fresh startup has no fictional records in the real mode.
- All app HTML/CSS/JS, icons and statement assets are served with an authenticated session.
- Product/customer creation, sale, partial receipt, overselling rejection, refund-confirmation rejection and confirmed return work through HTTP.
- Whole-sale deletion restores stock and cash effects; trash restoration reapplies the complete linked transaction.
- All five CSV export routes return UTF-8 BOM output.
- Backup download, later mutation and HTTP restore recover the expected prior stock and retain the pre-restore backup.
- A second launcher process detects the already-running instance.
- A complete process shutdown/restart preserves stock, invoice, payment and return data.

All tests use disposable directories and fictional records. No actual user PC or business records were accessed.

## Syntax and packaging

- Python modules compile successfully.
- `node --check` accepts all four JavaScript modules.
- Windows launchers use CRLF and UTF-8, with the main launcher switching to code page 65001.
- ZIP contains source, launchers, instructions and tests; no runtime database, session token, bytecode cache or third-party package directory is included.

## Not verified

- **Windows hardware execution and the .cmd double-click flow:** this environment is Linux; Windows was not available.
- **Rendered screen appearance, keyboard/click interactions, responsive layout and print pagination:** the available Browser security policy blocked both local HTTP and file URL navigation. No screenshot or visual QA completion is claimed.
- Large production datasets, hardware failure recovery, multi-device use, accounting compliance and integrations outside the documented scope have not been validated.

These results validate the listed accounting/data and HTTP flows, not every possible production scenario.
Use the separate demo mode to confirm the actual Windows/browser experience before entering live business transactions.
