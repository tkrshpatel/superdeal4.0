# Pre-production validation — 25 October 2026

Baseline: main `597899880d3e66aaeb1120c13227428b430ab94e`. This branch fixes validation infrastructure only; it does not change API configuration or merge the separate security branch.

## Confirmed from source and current GitHub results

| Area | Finding | Release implication |
| --- | --- | --- |
| Frontend | Current Mobile App workflow passed tests/build. This does not establish browser rendering or live PC behavior. | Run desktop/mobile acceptance on staging. |
| Python CI | Fails at collection because PyMongo and repository import paths were missing. | This branch adds the runtime dependency, test dependencies and paths. Fresh checks are required. |
| Backend coverage | Existing CI only selected tests/, leaving MongoDB/alert/transaction suites outside CI. | This branch provisions an isolated MongoDB replica set and runs the phase-2 suite too. Real provider tests remain excluded. |
| Android | Workflow tried adding an already tracked Android project and failed. | Generate only when absent, sync existing assets, then attempt APK build. |
| Dependency audit | Latest main build log reported 3 moderate and 1 high vulnerability. The earlier Vite fix is on feat/security-readiness. | Integrate reviewed dependency remediation before public launch; repeat audit for the release revision. |
| Deployment | Security branch's Caddy template rejects POST and omits alert routes. It also hardcodes API 8000. | Reconcile with .env API settings and permit only intended alert POST routes before using that template. |
| Fresh deals | Main.js has no periodic/visibility refresh; current data loads at startup and selected interactions. | An open page can miss newly published deals until refresh. |
| Alert signup | User observed HTTP 403 from the origin check. Exact trusted local origins were requested in .env. | Retest successful signup, confirmation, match and unsubscribe; the correction has not yet been confirmed on the PC. |
| Mail | Sender address selected: superdeals.helpdesk@gmail.com. No verified SMTP delivery evidence. | Configure credentials privately on the PC and test receipt before advertising active email alerts. |
| Runtime consistency | API/worker now load root .env, while existing environment variables still take precedence. | Verify actual running processes point to the same DB and published records; do not assume .env overrides stale terminal values. |

## Live end-to-end acceptance

Trace one newly received Telegram message through raw/PENDING, EarnKaro conversion, published product facts, API and webpage. Confirm exact affiliate link preservation and that EarnKaro values remain authoritative; browser research only fills verified missing values, and the LLM does not invent price/offer information. Verify coupon/code instructions appear without source/channel metadata.

Then opt in with an owned test address, confirm it, publish a matching controlled test deal, check one notification, ensure duplicate suppression, test daily quota and duration boundaries, and unsubscribe. Use an isolated staging database for synthetic records, not artificial production deals.

## Hosting checks required on the Windows PC

- Domain, HTTPS/tunnel routing and exact allowed origins; no Vite development server for public launch.
- Authenticated private MongoDB; verify public access cannot reach MongoDB, API admin routes, Ollama or local files.
- Isolate scraper browser network access from private/metadata addresses; DNS validation alone is not a network boundary.
- Restart/reboot recovery for API, Telegram and alert workers, MongoDB and tunnel; one processing runner per Telegram session.
- Back up MongoDB and restore into a separate test database; retain the previous deployable release for rollback.
- Check response latency and resource usage while Ollama/Playwright processing is active. Agree expected users/concurrency before choosing load-test thresholds.
- Validate responsive UI, missing images, filtering/search scope, save/share, unknown prices, strict >50% HOT badge and fresh/24-hour counters.
- Review final footer disclaimer/privacy/contact content. The user requested supplying the disclaimer later; it has not been finalized.

## Evidence boundaries

The chat execution environment is offline. This review used GitHub source and workflow logs; it is not a fresh local run or a test of the user's PC. Newly started GitHub workflow outcomes must be reviewed separately. No Telegram credentials, SMTP passwords, .env files, production subscriber data or session files are needed in chat. Real SMTP, production TLS/firewall, recovery, load and browser checks are still outstanding. No go-live approval is implied.

## Fresh GitHub results on validation branch

- Application regression suite: 174 passed on Python 3.11 and 3.12 after dependency/import-path repair.
- Frontend tests/build: passed.
- Backend collection uncovered a pre-existing API mismatch: test_image_candidates.py imports rank_candidates, but image_enrichment.py does not define it. The suite remains failing; this is not skipped or marked as passing.
- Follow-up validation uses --continue-on-collection-errors so other backend tests execute while preserving the collection error and failing exit status.
- Search/filtering currently runs over the 100 loaded cards, not the full database. Counts cover the full time window, so an absent search result does not establish that no matching deal exists.
