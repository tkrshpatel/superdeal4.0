# Coupon and deal instructions preview

Branch: `feat/earnkaro-deal-instructions`. No main changes.

## Try locally

Stop the worker, API and Vite before switching branches. Preserve any unrelated local edits.

```powershell
git fetch origin
git switch --track origin/feat/earnkaro-deal-instructions
cd app
npm.cmd ci
npm.cmd test
npm.cmd run dev -- --host 0.0.0.0 --port 5174
```

Restart the existing MongoDB API and Telegram runner from the repository root using the same commands and `.env` as before. MongoDB and Ollama should remain running. No migration is required.

Watch NEW published deals: existing fact records are deliberately unchanged. For an EarnKaro message containing an explicit coupon or usage instruction, the card shows a small badge. Open its product title to see How to get this deal, coupon codes with Copy code, conditions and expandable EarnKaro excerpts. Prices and affiliate links are untouched. Clipboard fallback selects the code when clipboard access is unavailable, including plain HTTP LAN pages.

## Source and association rules

- Deterministic extraction runs on the EarnKaro converted response after validation and before publication. No LLM-generated instructions or additional scraping is introduced.
- Terms live in a separate `deal_terms` field on published MongoDB facts, retaining the strict product schema and publication gate.
- Single-product, single-link messages can use relevant instruction lines anywhere in that converted message.
- Multiple-product messages require a self-contained paragraph with exactly one affiliate URL. Detached/global instructions, paragraphs containing multiple links, repeated-link ambiguity and links shared by multiple products are not assigned.
- Exact spelling and wording are retained, URLs omitted from displayed excerpts. Codes require explicit code cues; numeric discount amounts and common prose are rejected.
- A coupon mention without a code displays activation guidance, never a guessed code. Unsupported patterns may be omitted rather than guessed. This first version does not fall back to Playwright terms, because the current research snapshot does not carry structured coupon evidence.
- Instructions and conditions are plain escaped text; source messages cannot inject HTML or clickable instructions into the UI.
- Coupon, cashback and bank benefits are never deducted from selling prices.

## Validation

Backend extraction tests cover source preservation, code detection, coupon without code, ambiguous associations, shared links, bank/app restrictions, no-coupon wording and no price mutation. API tests verify published terms survive the legacy adapter. Frontend tests exercise the badge, detail rendering, Copy code, HTML escaping and unchanged price.

Production build and focused tests run without contacting real merchants, Telegram, EarnKaro or a live MongoDB replica set. Real message wording and phone layout still need local validation.
