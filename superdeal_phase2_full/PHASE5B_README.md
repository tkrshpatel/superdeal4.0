# Phase 5b — legacy filters and affiliate redirect

- `GET /deals`: q, merchant, min_price, max_price, sort=newest|price_asc|price_desc, limit. Publication-gated DB-side search.
- `GET /go/{id}`: 302 to unchanged first valid affiliate URL, records click in separate collection.
- `sort=popular` intentionally returns 400: historic click counts unavailable.
- Freshness, price history, verified prices and mobile deep-link behavior are NOT implemented.
- No Telegram monitoring or live external service calls in tests.
- Isolated backend only; existing app remains unchanged.

Run: `python -m pytest .\superdeal_phase2_full\test_phase5b.py -v`
