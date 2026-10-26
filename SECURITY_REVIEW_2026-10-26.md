# SuperDeals production security review — 26 October 2026

Base: main `0815fff7c6722a220fb8983735e85c547bf661ff`. Review branch: `phase-production-security`. This adapts the older security work to the current alerts, offer-facts, pagination and Telegram capture code. It does not merge the dropped category enhancement or the pending post-link price work. It does not change `.env`, API host/port defaults, historical data or deployed DNS.

## Confirmed issues addressed

- Unsafe stored redirect destinations could reach the Location header and click recorder. Validate HTTPS URL structure, credentials, controls, nonstandard ports, private literals, numeric IP encodings and local suffixes; keep accepted affiliate URL bytes unchanged. This is not verification of downstream retailer redirect chains or DNS ownership.
- Public responses formerly relied mainly on a denylist. Add deal/terms allowlists, nested offer-fact allowlists and provider-text filtering while preserving current price, effective-price and discount fields.
- API reads lacked request/query budgets and the server had unlimited worker threads. Bound per-client budgets, query fields/length, request URI/body sizes, socket waits and simultaneous workers. HEAD does not count affiliate clicks. Retain the existing email-alert limiter.
- Loopback proxies previously collapsed every visitor into one alert budget. A dedicated secret and canonical client-IP header are accepted only from authenticated loopback Caddy. Caddy overwrites client-supplied identity headers. Tunnel mode trusts Cloudflare's connecting-IP header only from its loopback connector.
- HTTP responses exposed Python versions and request query logs. Suppress those logs/banner and set no-referrer, nosniff, anti-framing and restrictive API CSP headers. Add page-level no-referrer and noreferrer links.
- The browser used a saved native API override even on the website. Restrict that setting to the native app. Restrict remote images to HTTPS and safe public API URL forms.
- Tighten service-worker caching so API/admin/redirect/query requests are not cached as static assets, and expire only this application's old shell caches.
- Public API startup formerly initialized raw ingestion/worker collections. Add public-only index initialization and a collection-scoped Mongo API role template; worker collections remain worker-managed.
- The old deployment template rejected all POST requests and hardcoded an API port. New Caddy configurations permit the three alert POST routes, block public admin/private-file routes and serve only `app/dist`. The launcher derives the upstream from existing `.env` API settings and passes Caddy only its required environment. Production mode fails closed on remote API binding or weak/shared admin/proxy tokens.

## Dependencies

- Upgrade Vite to the patched 7.3.7 line.
- Use the npm-audit-recommended compatible Capacitor CLI 8.4.3 to remove its vulnerable xcode/uuid dependency chain. Native plugin versions remain unchanged. Android asset sync passed locally; complete APK compilation is checked by CI.
- Raise pytest's supported minimum to 9.0.3 and update the isolated audit environment's pip. These were the two packages with reported Python environment advisories; runtime dependencies were already clear in that fresh resolution.
- Final local npm audit: zero known advisories, including development dependencies.
- Final local pip-audit after tool updates: zero known advisories in the isolated environment. This does not certify packages installed on the Windows PC. Re-run the audits there before launch.

## Local verification

- 375 application, HTTP/security, alert, privacy and real-Caddy proxy tests passed together.
- All 49 frontend tests and the production build passed. Capacitor Android sync passed.
- Both direct HTTPS and loopback tunnel Caddy configurations validated using checksum-verified Caddy 2.11.7.
- Actual Caddy -> API tests covered static serving, security headers, blocked private/admin paths, all alert routes, POST method restrictions, forged identity headers and alert rate limits. These tests use a synthetic Mongo-compatible backend and do not send email.
- Gitleaks scanned 153 reachable repository commits with no detected leaks. A separate redacted scan checks the current files. This is pattern-based detection, not proof that no sensitive data has ever existed.
- Bandit was run across active and legacy Python sources. No high-severity findings were reported. Medium flags were reviewed: the legacy SQL query uses parameter values plus fixed sort/condition fragments; Telegram Bot URLs are constructed with a fixed HTTPS API origin; the legacy urllib enrichment path is outside this production entry point; test URL calls target disposable local servers. These flags are not represented as a blanket clean static analysis result.
- A real MongoDB server could not start in this execution environment (`open: Operation not permitted`). The full Mongo replica-set/publication/transaction suite is delegated to the existing GitHub Actions Mongo service, not replaced with mocks or skipped.
- Chromium download returned a truncated archive, so a real-browser CSP pass was not completed here. DOM/interaction tests and real HTTP proxy tests pass; live-browser acceptance remains required.

## Existing test-suite repair

The earlier nine backend failures used a legacy URL-shaped LLM fixture despite production requiring opaque link IDs. Fixtures now adapt to the strict existing contract; invented links still fail closed. Multi-product transaction fixtures use distinct names to avoid the intentional duplicate-product gate, and price-search fixtures include source prices rather than unsupported model-only numbers.

The former image collection error imported a helper that does not exist in the shipped API. The test now exercises the actual candidate_urls safety/ranking interface, product immutability and source ambiguity. No image-ranking or price-parsing feature was added to production code to satisfy stale tests.

## GitHub Actions verification

Verified code commit `201b07026838aa72fae454ac2306bd9aa9bbddde`:

- Full application and MongoDB replica-set/backend suites pass on Python 3.11 and 3.12. The prior nine fixture failures and image import collection error are resolved. The proxy test is conditional in the generic application job; the dedicated security job supplies Caddy and runs it explicitly.
- Security/dependency/secret-scan/real-proxy workflow passes.
- Frontend tests and production build pass.
- Full Android debug APK build passes with the audited dependency versions.
- The environment-loading test now exercises the bounded server/public-only startup API while still asserting that existing .env host/port values are preserved.

These are code/staging checks, not verification of the actual Windows host or public domain.

## Hosting readiness and remaining launch gates

Prepared deployment: GoDaddy domain registration + Cloudflare DNS/Tunnel + Windows PC origin, with a separate direct-TLS Caddy option. See `deploy/README.md`, `deploy/hosting.env.example`, `scripts/hosting.py` and `scripts/check_public_security.py`.

Not yet verified and still required before public launch:

1. Actual domain, DNS ownership/nameservers, public HTTPS certificate/redirect and edge limits. No account, DNS, firewall or public host has been modified or scanned.
2. Windows-specific application versions, service identities, private listeners and external firewall exposure. No router forwarding is needed for the tunnel path. Remove temporary LAN development rules after testing.
3. Mongo authentication/least privilege, protected credentials/session files, backup restore and reboot recovery. API and worker credentials should be separated in their private process environments.
4. Scraper worker egress isolation. URL/DNS checks alone do not eliminate DNS-rebinding/TOCTOU or subsequent connection-resolution risks. The browser must be unable to reach private/loopback/link-local/metadata destinations from its actual worker environment. This is a launch gate, not a solved problem declared by an environment flag.
5. Real SMTP sender/authentication, opt-in confirmation, unsubscribe and quota tests with the owner's address. Dry-run email files are not sent emails.
6. Full browser flows under deployed CSP: product images, search/filter/pagination, exact Shop navigation, signup/confirmation/stop and service-worker upgrades.
7. Live Telegram -> captured inbox -> publication -> website -> email, and reconnect/restart checks. Historical publications must not be replayed for this validation.

This is a source/dependency/local boundary assessment, not a penetration-test certification or a claim of complete security. The branch is prepared for controlled staging; public production clearance depends on the host checks above.

References: OWASP SSRF Prevention and Unvalidated Redirects cheat sheets; Caddy reverse_proxy/Caddyfile documentation; Cloudflare Tunnel setup/Windows service documentation; GoDaddy nameserver help. Exact links are in `deploy/README.md`.
