# Synchronous image enrichment (local-only)

Publication order: Telegram raw → EarnKaro → Mistral → validation → Playwright image enrichment → **atomic MongoDB publication**. There is no watch process, backfill, or asynchronous job.

For each product, Playwright attempts to extract a real product image from a uniquely identifiable original merchant URL. It never navigates EarnKaro affiliate links. If an image is unavailable, the stored `image_enrichment` object is `{status: PLACEHOLDER, image_url: /superdeal-placeholder.svg}`. The placeholder is served by Vite from `app/public/`.

Install with `python -m pip install playwright` and `python -m playwright install chromium`. Start the usual API, Telegram worker and Vite; no additional worker. A merchant browser timeout may delay publication, but does not fail it. Other validation failures still block publication, and no failed message is retried automatically.

Test: `python -m pytest -q superdeal_phase2_full/test_image_enrichment_sync.py`. Old already-published deals are not modified by this patch; the UI uses the placeholder when image_url is missing. No GitHub updates.
