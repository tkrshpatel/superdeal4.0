# Shopper frontend refresh

Branch: `feat/shopper-frontend-refresh`. Main is not modified.

## Run on Windows

From the repository root, stop the old Vite process and run:

```powershell
git fetch origin
git switch feat/shopper-frontend-refresh
cd app
npm ci
npm test
npm run dev -- --host 0.0.0.0 --port 5174
```

Keep the existing API running. The Vite proxy still uses port 8000 by default; set `SUPERDEAL_PREVIEW_API` to the existing API address if needed. Restart the phase2 API to pick up the image adapter fix. No database migration or automatic reprocessing is performed.

## Changes

- Published backend images now survive the legacy `/deals` adapter. The old adapter discarded every image URL.
- Smaller, deliberate fallback cards; failed images degrade gracefully. Existing blocked/missing image evidence remains unknown.
- More readable product titles, prices and retailer labels; rounded calculated discounts and rupee savings only with a usable price pair; no empty MRP labels or low click-count clutter.
- Retailer-specific buttons, recognizable share icon, absolute share links, copied-link feedback, saved states and clickable cards with accessible title buttons.
- Store filters, category filters only when the API supplies categories, matching offer counts, loading and retry states.
- Detail dialog with keyboard focus management, optional supported description and conditions, explicit posted/checked timestamps and affiliate disclosure.
- Responsive layout, visible keyboard focus and reduced-motion support.
- Offline service worker no longer caches price API requests or affiliate redirects.

## Source rules

The existing LLM prompt already requires EarnKaro first, exact-link Playwright second, and no invented facts. The frontend uses published product names ahead of scraped page titles, original merchant fields ahead of enriched fields, and does not consume `llm_*` prices. Selling-price reconciliation now also clears unsupported model prices and replaces them with exact-link browser evidence only when EarnKaro lacks a clear price. Original Telegram text is no longer a hidden price fallback. Affiliate URLs are unchanged and `/go/:id` still handles redirects.

The LLM remains the existing evidence-bound extraction/formatting step for names, merchant and original-price fields; this branch does not introduce a new extraction engine. Missing titles are not embellished with invented product specifications. Existing published records are not rewritten. No fabricated price history, discount alerts or sale claims are added. Unknown offers retain the neutral “Offer” label; a precise sale/coupon type requires explicit source fields.

## Validation

- Frontend: 7 tests, including synthetic DOM shopping flows, filtering, saving, focus restoration, image errors, retries, source precedence and HTML escaping.
- Production Vite build and diff whitespace check pass.
- Focused backend/API/source-priority tests pass (see handoff for count).
- Live merchant extraction, live MongoDB replica-set integration, Android APK and actual-device visual verification were not run. Browser installation failed in this environment.
- A broader existing image test cannot collect: `test_image_candidates.py` imports `rank_candidates`, which is absent from the current image module. This branch does not modify that module.

Synthetic DOM tests verify behavior, not pixel layout. Review on the phone and desktop before merging. No deployment or merge is performed.
