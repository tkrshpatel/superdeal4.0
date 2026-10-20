# Phase 7 isolated integration candidate

This is a **patch package**, not a production deployment. Only copy files after reviewing paths.

## Changes
- MongoDB `legacy_search(sort="popular")` ranks published offers by **observed** `/go` clicks in the last 24 hours. This does not imply complete click history.
- Capacitor Android opens `/go/{id}` with `@capacitor/browser` instead of an embedded WebView popup. Android/browser may open installed shopping apps when the destination supports app links; this is not guaranteed.
- Detail-sheet and deal-card buttons use the same redirect flow. Browser site remains unchanged.
- Existing Phase 6 timezone fix retained.
- No changes to EarnKaro source URLs, Telegram reader, or live SQLite app.

## Apply to Windows project
Copy `superdeal_phase2_full/backend.py` to the matching folder. Copy `app/src/main.js` and `app/package.json` to matching paths. Do not replace other files.

From project root, with MongoDB rs0 running:
```powershell
python -m pytest .\superdeal_phase2_full\ --ignore=.\superdeal_phase2_full\test_mistral_live.py -v
```
From `app`:
```powershell
npm install
npm test
npm run build
npx cap sync android
```
`npm install` will update package-lock.json locally. Android build/device test still required.

## Scope limits
- Physical phone API access requires a securely reachable PC/server endpoint; localhost is not reachable from a phone. Current backend disallows remote HTTP without explicit authorization/TLS reverse proxy. Do not enable remote HTTP on public networks.
- `fresh` currently indicates publication age, not independently verified merchant availability or price. UI 24h listing cutoff still requires product decision and implementation.
- No GitHub changes, CI runs, Telegram monitoring or production switches were performed.
