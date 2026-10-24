# Product deal alerts

Branch: `feat/product-deal-alerts`, based on main's logo/layout changes. The separate security-readiness branch has not been merged.

## Shopper flow

Click **Get notified** above search, or **Get notified about this product** inside a deal. Enter the product/model, email, maximum emails per day (1, 2, 3 or 5), duration (1–30 days), and consent.

An email confirmation activates the alert. Duration begins at confirmation, not signup. Confirmation expires after 24 hours. Every deal email has an unsubscribe link. No matching new deal means no email; the selected frequency is a maximum, not a promised number of reminders. Each request has its own limit; a recipient can have at most five live requests.

Default mode is **dry-run** with placeholder sender `SuperDeals <alerts@superdeals.invalid>`. It writes private `.eml` previews and never contacts SMTP. The UI explicitly says no email has been sent. Email addresses and subscriptions are stored in MongoDB; they are not exposed by a public list endpoint.

## Windows local test

Keep your existing MongoDB URI/database and API settings in the repository `.env`. These commands do not start Telegram, EarnKaro, Playwright or Ollama. Keep your existing pipeline running if you want new deals to arrive.

```powershell
cd C:\Users\Home\superdeal4.0
git fetch origin
git switch --track origin/feat/product-deal-alerts
.\.venv\Scripts\python.exe -m pip install -r .\superdeal_phase2_full\requirements.txt
$env:SUPERDEAL_EMAIL_MODE = 'dry-run'
$env:SUPERDEAL_PUBLIC_URL = 'http://localhost:5174'
# If not already present in this terminal:
if (-not $env:SUPERDEAL_ADMIN_TOKEN) { $env:SUPERDEAL_ADMIN_TOKEN = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))" }
.\.venv\Scripts\python.exe .\superdeal_phase2_full\api.py
```

In a second PowerShell terminal:

```powershell
cd C:\Users\Home\superdeal4.0\app
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1 --port 5174
```

Open `http://localhost:5174`. Submit an alert with your email and an actual product/model. In a third terminal, using the same MongoDB environment:

```powershell
cd C:\Users\Home\superdeal4.0
$env:SUPERDEAL_EMAIL_MODE = 'dry-run'
$env:SUPERDEAL_PUBLIC_URL = 'http://localhost:5174'
.\.venv\Scripts\python.exe .\superdeal_phase2_full\notifications.py --once
Get-ChildItem .\data\notification-previews\*.eml | Sort-Object LastWriteTime -Descending
```

Open the latest `.eml` in an email viewer, follow its confirmation link and click **Activate my alert**. Run `notifications.py --once` again. If a matching committed deal was published during the last 24 hours, a second `.eml` preview contains the deal. Otherwise the alert remains active and waits. Re-running must not preview the same deal twice. The unsubscribe link opens a confirmation screen; click **Unsubscribe** to stop that product alert.

For continuous processing, omit `--once`. Polling runs every minute. No Windows scheduled task/service is installed automatically. The API and notification worker automatically load the repository `.env`, using the same precedence as the Telegram runner: existing terminal variables win. API host/port, MongoDB and other existing defaults are unchanged. Restart processes after editing `.env`; remove stale terminal overrides if they point to a different database. Do not use the legacy `start_superdeal_api.bat`, which starts the older backend.

## Matching and scheduling

- Deterministic Unicode/case/spacing/token normalization; no LLM is used to match or invent deals. `iPhone17 Pro` matches `iPhone 17 Pro`.
- All requested tokens must occur in the published product name. Extra model suffixes (Pro, Max, Plus, Mini, Ultra, Air, Lite, FE, SE), accessories and renewed/refurbished listings are conservatively excluded unless requested. This can miss ambiguous or incomplete names; it is not semantic product identification.
- Only existing committed, publication-gated deals from the past 24 hours are considered. The worker scans those deals independently of the frontend card limit. Prices come from published `deal_price`; absent prices say to view the retailer. Affiliate links use the existing `/go/{id}` route without changing the stored URL.
- A batch includes up to 10 previously unnotified matching deal IDs. Duplicate detection is per alert and deal ID, not a cross-store SKU catalog. A republished distinct ID can notify again.
- Limits reset at midnight IST. Emails are also spaced by at least `24 hours / selected maximum`, so alerts may send fewer emails even when a backlog exists.
- MongoDB atomic leases coordinate workers; quota is reserved before sending, and unique delivery IDs prevent re-sending reserved deals. An uncertain SMTP outcome or a crash after reservation is **not retried automatically**. A quota slot can be consumed without an email; delivery is not guaranteed. A cancellation cannot retract an email already in flight.
- Confirmation failures also require manual investigation/new signup after expiry rather than automatic repeated email attempts.

## Real email later

Configure these variables in both the API and worker environments, restart both, and verify your sender with the chosen provider:

```text
SUPERDEAL_EMAIL_MODE=smtp
SUPERDEAL_PUBLIC_URL=https://YOUR-DOMAIN
SUPERDEAL_EMAIL_FROM=SuperDeals <alerts@YOUR-DOMAIN>
SUPERDEAL_SMTP_HOST=YOUR-SMTP-HOST
SUPERDEAL_SMTP_PORT=587
SUPERDEAL_SMTP_USER=YOUR-SMTP-USER
SUPERDEAL_SMTP_PASSWORD=YOUR-SMTP-PASSWORD
```

SMTP requires STARTTLS, authenticated credentials, a real sender and an HTTPS public URL. Add provider DNS authentication and test deliverability before enabling customer traffic. Previously previewed deliveries stay deduplicated when switching modes; create a fresh test request/deal for SMTP testing.

A deployment proxy must forward **POST** `/api/v1/alerts`, `/api/v1/alerts/confirm` and `/api/v1/alerts/stop` to the API. The security branch's current Caddy template blocks POST and must be updated before combining/releasing this feature. The Vite proxy in this branch already supports these endpoints for local testing.

## Data and operational boundaries

Mongo collections: `deal_alerts` (recipient/preferences/consent/status), `alert_confirmations` (private queued confirmation), `alert_deliveries` (dedupe and outcome). Confirmation tokens are hashed in subscriptions; queued messages and unsubscribe links contain private bearer tokens and require database access control. Do not publish or commit preview files. Subscriber email addresses and unsubscribe tokens are personal/private data, not anonymous data.

Pending alerts expire after one day; confirmed alerts expire at the selected duration. TTL cleanup removes subscriptions 30 days after expiry, confirmations after 2 days, deliveries after 60 days. MongoDB TTL cleanup is asynchronous; expiry/status checks apply immediately in the application. Preview files require manual deletion after testing and must stay outside the web root. A dedicated least-privilege MongoDB user needs access to these three additional collections.

New POST routes enforce JSON, a 4 KiB body limit, same-origin/explicit-origin checks and a bounded 12-requests/hour peer budget. Production needs edge per-client throttling and bot controls: behind a proxy, clients share the peer budget. Configure `SUPERDEAL_ALERT_ORIGINS` as comma-separated exact trusted origins if needed; it is not CORS configuration. Native cross-origin use needs a separately reviewed CORS policy. There is no public subscriber-list endpoint. Confirmation and unsubscribe tokens use fragments and explicit user actions to avoid activation by link scanners.

## Verification

Install optional test dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\superdeal_phase2_full\requirements-notification-tests.txt
$env:PYTHONPATH = 'superdeal_phase2_full;src;.'
.\.venv\Scripts\python.exe -m pytest .\superdeal_phase2_full\test_notifications.py .\superdeal_phase2_full\test_api.py .\superdeal_phase2_full\test_public_presentation.py .\superdeal_phase2_full\test_phase5.py
npm.cmd test --prefix app
npm.cmd run build --prefix app
```

The isolated alert tests use mongomock, including concurrent worker claims and loopback HTTP requests. They do not establish real MongoDB index/TTL performance, SMTP delivery, firewall configuration or production readiness. Test those on staging before public release.

Local results: 28 alert/backend tests plus 10 API/presentation regression tests passed; the separate 174-test application suite passed. All 23 frontend tests and the production build passed. Browser screenshot validation could not run because the Chromium download failed, so a visual check on your PC remains necessary. No real recipient was emailed.
