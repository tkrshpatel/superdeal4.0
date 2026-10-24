# Pre-launch security review

Reviewed main commit `c94e9d37c1818861eb77cd8fc197e14f625e3bae`. This is a source review and local automated assessment, not a penetration-test certification. No public production host was supplied or tested. Main and the running site have not been changed.

## Changes

- Validate stored outbound destinations before redirecting or recording clicks. Reject non-HTTPS, credentials, control characters, private literal addresses, local hostnames and unusual ports while preserving valid affiliate URLs exactly. This does not validate subsequent affiliate redirect chains.
- Add bounded per-peer request budgets, query limits, socket timeouts, generic validation errors and API response security headers. Suppress request query logging and Python version banners.
- Publish explicit deal and coupon field allowlists instead of arbitrary stored metadata. Existing provider/channel text filtering remains; unknown channel names embedded in ordinary prose are not guaranteed to be recognized.
- Stop the service worker intercepting/caching API, admin, redirect or query requests, and expire old shell caches.
- Restrict saved API-origin overrides to the native app. Add no-referrer handling to the web page and outbound links.
- Upgrade Vite from 7.3.6 to 7.3.7 and Capacitor CLI from 8.5.2 to 8.5.3.
- Prepare `deploy/Caddyfile` for HTTPS, CSP, sensitive-path blocking, private API proxying and serving only `app/dist`. Caddy is not installed here: this template has not been validated or exercised.
- Add `scripts/check_public_security.py`, a read-only HTTPS smoke check. It deliberately avoids affiliate clicks.

## Verification

- Python `tests/` suite: 174 tests passed.
- Focused phase-2 HTTP/API/public-presentation/coupon/count suite: 45 tests passed, including real loopback HTTP requests, unsafe redirects, spoofed forwarding headers, unauthenticated admin access and rate limits.
- Frontend: all 18 tests passed; production Vite build passed.
- npm audit: zero critical/high findings after updates. Three moderate findings remain in the Capacitor CLI / xcode / uuid iOS build-tool chain. No advisories reported by `npm audit --omit=dev`. Do not force a UUID major-version override without compatibility verification.
- pip-audit: zero known advisories across 15 freshly resolved manifest dependencies including PyMongo. This does not establish the versions/security of the user's installed production virtual environment.
- Targeted high-confidence secret-pattern scan of current tracked files: no matches. Git history, entropy-based detection and external credentials were not audited.

Python suites must run separately because both directories contain a module named `test_api.py` under the repository's current pytest import configuration:

```sh
PYTHONPATH=superdeal_phase2_full:src:. python -m pytest -q tests
PYTHONPATH=superdeal_phase2_full:src:. python -m pytest -q superdeal_phase2_full/test_http_security.py superdeal_phase2_full/test_public_presentation.py superdeal_phase2_full/test_api.py superdeal_phase2_full/test_phase5.py superdeal_phase2_full/test_deal_terms.py superdeal_phase2_full/test_deal_window_counts.py
npm ci --prefix app
npm test --prefix app
npm run build --prefix app
```

## Required deployment verification

1. Supply the domain and hosting environment. Serve the built frontend over HTTPS; do not expose the Vite development server. Set `SUPERDEAL_DOMAIN` and `SUPERDEAL_DIST`, then run `caddy validate --config deploy/Caddyfile --adapter caddyfile` before loading it. Exercise browser flows under CSP, including images, filters, coupons and affiliate redirects.
2. Keep API port 8000, MongoDB 27017, Ollama 11434 and Caddy administration 2019 private. Bind the API to loopback. Verify firewall rules from outside the server. Use authenticated MongoDB, least-privilege service credentials and tested backups. Give the public API only the credentials it needs, separate from Telegram/EarnKaro worker secrets.
3. Isolate the scraper browser at the network boundary. Existing request interception and DNS checks reject private results, but separate browser DNS resolution and cached checks leave a DNS-rebinding/TOCTOU risk. Confirm worker egress restrictions against loopback/private/link-local/metadata targets while preserving explicitly required service access. Application validation alone is insufficient here.
4. Configure edge per-client throttling appropriate to hosting and expected traffic. The bounded application budget keys on the real peer, never forwarded headers; behind a loopback proxy all visitors share that budget. It is not distributed denial-of-service protection.
5. Run `python scripts/check_public_security.py https://YOUR-DOMAIN` from a separate machine, inspect TLS, confirm sensitive routes are unavailable, and verify the deployed dependency versions. The smoke script checks only a small defined set of paths and headers.

Existing repository CI configuration and Android packaging were not repaired by this review. No live MongoDB integration, production firewall, backup restore, browser CSP, or public-host test has been performed. Launch readiness remains conditional on these host checks.

References: [OWASP HTTP headers](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html), [OWASP CSP](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html), [OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html), [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
