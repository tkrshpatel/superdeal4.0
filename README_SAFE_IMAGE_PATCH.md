# SuperDeal image enrichment — reviewed patch

This ZIP contains **only** `image_enrichment.py`, `test_image_enrichment_regression.py`, and this README. It makes no modifications to product mapping, backend.py, prompts, EarnKaro, or the frontend.

## What we discovered

The restored module had a fixed merchant allowlist which did not include `fkrt.cc`, and it discarded original Telegram links that also appeared in the affiliate URL list. The fallback had no failure reason. A generic scraper must not guess which of several original links belongs to an individual product.

## Installation on Windows

1. **Stop the Telegram worker.** Leave the existing code intact until tests pass.
2. Download ZIP into Downloads, unzip it into a **temporary review folder** first, rather than immediately overwriting the running module.
3. Back up `C:\Users\Home\superdeal3.0\superdeal_phase2_full\image_enrichment.py` to `image_enrichment.py.before_safe_patch`.
4. Copy just the ZIP's `image_enrichment.py` and `test_image_enrichment_regression.py` into `superdeal_phase2_full`.
5. Run `cd C:\Users\Home\superdeal3.0; .\.venv\Scripts\python.exe -m pytest -q .\superdeal_phase2_full\test_image_enrichment_sync.py .\superdeal_phase2_full\test_universal_image_enrichment.py .\superdeal_phase2_full\test_image_enrichment_regression.py`.
6. Only if the tests pass, restart the worker, inspect the image diagnostics from a new `fact_table` entry and verify the product name and affiliate URLs against original EarnKaro output.

To roll back, stop worker and copy `image_enrichment.py.before_safe_patch` over `image_enrichment.py`.

## Constraints and known limitations

- This is synchronous, uses Playwright and does not retry or backfill published deals.
- Reads raw Telegram URLs, never navigates EarnKaro-only URLs, never changes products or affiliate links.
- Multiple products with unrelated short links are **not** guessed. They receive placeholders until deterministic source-link association is available. Correct product links are more important than images.
- Browser redirects, DNS policies, anti-bot restrictions and merchant hotlinking may still cause placeholders. `image_enrichment.diagnostics.reason` identifies the fallback reason.
- Browser checks are live only when running against a real merchant; our tests are offline and do not prove live compatibility.
- `safe_url` + public-DNS checks are best-effort: running external-site browsers carries network risk. Keep the worker on a trusted, restricted host.
