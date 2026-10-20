# Phase 5 — read-only legacy compatibility prototype

Adds `GET /deals` and `GET /deals/{MongoObjectId}` with the old response field names. These are **not** a full drop-in replacement. Existing UI may require integer IDs, sorting, search, click redirects, freshness, price history, intelligence, and image URLs. Those are intentionally NOT fabricated. Unsupported legacy filters return HTTP 400 rather than being ignored. `fresh_window_hours` is `null` because no equivalent 24-hour filtering exists. Do not switch the frontend yet.

Test: `python -m pytest .\superdeal_phase2_full\ -v --ignore=.\superdeal_phase2_full\test_mistral_live.py`

No Telegram activity, no website/mobile changes, no GitHub merge.
