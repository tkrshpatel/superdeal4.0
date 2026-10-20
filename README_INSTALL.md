# SuperDeal — universal synchronous image enrichment patch

Replaces only `superdeal_phase2_full/image_enrichment.py`. It is compatible with the existing synchronous publication integration (`enrich_products(...)`). No backend, Telegram, EarnKaro, frontend, or database migration changes.

## Windows PowerShell

Stop Telegram worker before installing. From `C:\Users\Home\superdeal3.0`:

```powershell
Copy-Item .\superdeal_phase2_full\image_enrichment.py .\superdeal_phase2_full\image_enrichment.py.bak
Expand-Archive "$env:USERPROFILE\Downloads\superdeal_universal_image_enrichment_patch.zip" -DestinationPath . -Force
.\.venv\Scripts\python.exe -m pytest -q .\superdeal_phase2_full\test_universal_image_enrichment.py
```

Restart the Telegram worker only after tests pass. Existing published deals are not changed. New deals are enriched synchronously before publication.

## Behavior

- Uses original Telegram URLs only, not new EarnKaro URLs. Works with arbitrary HTTPS merchant hostnames, including Flipkart and independent stores.
- For multiple original links, an exact match to a product link is required; otherwise the product receives a diagnosed placeholder rather than a wrong sibling image.
- Extracts Product JSON-LD, Open Graph / Twitter images, and product-oriented DOM images; verifies browser decoding and minimum 120x120 dimensions.
- Normalizes Flipkart `{@width}` and `{@height}` to 800.
- Stores `image_enrichment.diagnostics` with `reason`, `source_host`, `resolved_host`, `http_status`, `candidates`, `checked` (no source URL query parameters).
- `FOUND` and `PLACEHOLDER` statuses remain compatible with existing backend and frontend.

## Known limitations

- Some stores block headless browsers, require login, or load images after the DOM becomes ready; those may still fall back to a placeholder.
- Browser URL restrictions prevent direct private-IP URLs and common internal hostnames but are not a complete network-level SSRF sandbox. Run against untrusted links only in a network-restricted worker environment.
- The URL-to-product association remains conservative for multi-product messages.
- Unit tests use a mocked scraper. Live merchant browser tests must be performed on the user's machine.
