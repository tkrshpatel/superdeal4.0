# Source-backed price and discount scenarios

Branch: phase-offer-evidence. Based on phase-24-hour-feed. Main, API host/port, .env and production records are unchanged.

## Public behavior

| Evidence | Display |
| --- | --- |
| Clear source selling price and MRP | Both prices, calculated discount and monetary savings |
| Source price and exact percentage, no MRP | Price and stated percentage; no inferred MRP or savings amount |
| Exact percentage only | Percentage and retailer-price prompt; exact >50% qualifies as HOT |
| Up-to percentage only | Preserve Up to; never HOT from the upper bound alone |
| Up-to headline plus known price pair | Calculated product discount, with advertised Up to offer separately in details |
| Coupon, bank, cashback or additional discount | Separate conditional label and existing coupon/eligibility instructions; never add to base discount |
| Missing source fields and verified exact-link browser fields | Browser fills missing values only; unverified model values cannot fill them |
| Conflicting source/browser facts | Source wins; do not infer an MRP from price + percentage |
| Internally inconsistent source percentage and source price pair | Use the clear numerical source price pair and record a private conflict |
| Ambiguous prices or product/link association | Omit ambiguous fields; do not transfer another product's offer |
| Explicit monetary savings without MRP | Preserve the stated savings amount; do not treat it as a selling price or invent an MRP |\n| Missing reliable values | Retailer-price prompt; no invented savings or discount |

The matcher recognizes explicit INR price/MRP labels, Indian and international comma-grouped INR amounts, flat/exact/Up to discount phrases and conditional discount contexts. Ambiguous or unrecognized formats are intentionally omitted. It is not an unrestricted natural-language interpreter. Known foreign currency lines and effective/after-benefit prices are not treated as unconditional INR prices.

Strict HOT uses the unrounded verified discount: 50% is not HOT; 50.1% is. Coupon/bank benefits and Up to percentages alone never qualify. The 50%+ filter also excludes upper-bound-only offers.

## Pipeline and existing records

The model still returns formatting and opaque link IDs. Deterministic offer_evidence.py resolves canonical selling price, MRP and discount after validation, before publication. New facts keep private source/conflict diagnostics separately; public APIs expose a small offer_facts contract with numerical values, qualification and generic conditional labels. No source/channel attribution is shown.

Existing published records can recover facts at read time from their stored converted source message and optional, correctly associated stored browser evidence. This is read-only; no replay, duplicate product, new provider call or bulk rewrite is needed. A bounded per-publication cache is refreshed on process restart. Records without saved converted evidence retain the previous price-pair compatibility display and cannot acquire a standalone verified percentage. Exact historical evidence cannot be reconstructed when it was never stored.

The strict public allowlist on the separate security-readiness branch will need offer_facts added when that branch is integrated. That branch has not been merged here.

## Verification

Scenario tests cover source-only percentages, missing values, qualified offers, source/browser conflicts, association, privacy, conditional arithmetic and legacy-record recovery. Real MongoDB publication testing checks that an invented model price/MRP is replaced by source facts, the exact affiliate URL survives and internal provenance is excluded from shopper output. Frontend tests exercise cards, details, filtering and HOT thresholds.

Known pre-existing validation failures remain tracked in RELEASE_VALIDATION.md. Review current GitHub results before merging; no production readiness claim is implied.

## Verified GitHub results

Implementation revision: `d920a4ee4f768f31b7835d27f74f1acab8706239`.

- Application/scenario suite: **222 passed** on Python 3.11 and 3.12.
- Frontend: **36 passed**, production build passed.
- Expanded MongoDB suite: **110 passed**, with the same **9 legacy-contract failures and 1 image-test collection error** already tracked in the release review.
- New tests include actual publication of an exact-discount-only deal with invented model prices removed, strict API HOT qualification, untouched affiliate URL and private provenance exclusion.
- The chat execution environment remains offline; these are GitHub-hosted results, not a test of the user's Windows PC or real email delivery.

Evidence: [Python and MongoDB run](https://github.com/tkrshpatel/superdeal4.0/actions/runs/40187519580), [frontend run](https://github.com/tkrshpatel/superdeal4.0/actions/runs/40187519608).

Local review: fetch/switch phase-offer-evidence, restart the API with the existing .env and refresh the frontend. Existing records with saved source evidence recover at read time; no ingestion replay is required. Do not merge for production until the outstanding release blockers are resolved.
