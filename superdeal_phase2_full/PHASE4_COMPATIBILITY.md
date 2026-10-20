# SuperDeal Phase 4 — integration contract review

## Confirmed differences (existing GitHub API vs isolated MongoDB API)

| Existing website API | MongoDB API | Required action |
|---|---|---|
| GET /deals -> {deals, fresh_window_hours} | GET /api/v1/deals -> {items, limit, offset, has_more} | Add frontend adapter or versioned compatibility route |
| GET /deals/{integer_id} | GET /api/v1/deals/{ObjectId} | Update frontend ID handling; do not coerce ObjectIds to integers |
| current_price | deal_price | Map field |
| merchant | ecommerce_platform | Map field (semantic differences must be checked) |
| affiliate_url | affiliate_urls[] | Choose exact valid URL; preserve bytes |
| GET /go/{id} (click tracking + redirect) | Not implemented | Preserve deep link/app-first routing and click tracking before switch |
| price-history/intelligence/freshness endpoints | Not implemented | Explicitly decide replacements, no fabricated history |
| q, merchant, min_price, max_price, sort | Not implemented | Add and test before switching frontend |
| freshness 24-hour cutoff | No cutoff | Decide policy before switching |

## Scope

- Phase 4 adds MongoDB-side pagination and indexed ID lookup for /api/v1/deals only.
- Published status + publication_id are checked in aggregation; transactional commit remains the publication invariant.
- No web/mobile source modifications. No Telegram monitoring. No GitHub merge.
- This is not yet a completed web/mobile integration; the above contract gaps are blockers.
- Verify the exact current mobile app contract separately before any rollout.
