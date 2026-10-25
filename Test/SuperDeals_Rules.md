# SuperDeals message rules

These are required contracts, exercised by tests/test_owner_message_contracts.py, tests/test_offer_evidence.py and tests/test_category_offers.py.

- EarnKaro is authoritative; exact-link Playwright evidence fills missing values. The model formats, never invents prices or URLs.
- Shared headline product context, discounts and conditions accompany each applicable row, including a primary unlabelled collection link.
- Row labels qualify the headline: PUMA Shoes + Women becomes PUMA Women's Shoes. Preserve exact per-product affiliate links.
- @number, Rs/INR amounts and standalone quotes are selling-price evidence; associate each quote with its own link. Preserve punctuation, inline and multi-line formats.
- Starting prices show From. Explicit effective/card prices keep their conditions. Conditional savings are separate and never automatically deducted.
- Flat discounts are exact; Up to remains an upper bound. Monetary discount labels include off; cashback remains cashback. Never invent MRP.
- HOT requires a posting within 30 minutes and an exact discount above 75%; exactly 75% and Up to claims do not qualify.
- No price evidence means View price at retailer. Do not fill a price using model guesses.
- No EarnKaro/Telegram/channel metadata on the shopper UI. Keep fixed card geometry, standard price typography and button-only hover.
- Enhancements apply to new processing only. Read paths return stored publication facts and terms; no replay, renaming, splitting or backfill of history.
- .env and API configuration remain unchanged. Main changes require a separate merge instruction.
