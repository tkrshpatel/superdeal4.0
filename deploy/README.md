# Windows hosting with a GoDaddy domain

The prepared route is GoDaddy as registrar, Cloudflare DNS/Tunnel as the HTTPS entry point, and your Windows PC as origin. This does not upload a Python/Mongo/Telegram backend into a GoDaddy website-builder or shared-hosting folder. If you buy actual GoDaddy hosting instead of only a domain, confirm the exact plan/VPS and supported long-running processes first.

No DNS, account, domain, firewall or live service has been changed by these files. Main is not automatically updated.

## 1. Prepare locally

Keep existing root `.env` API host/port/database configuration. Merge the settings in `deploy/hosting.env.example` into it; do not overwrite `.env`. Use your real domain, unique admin/proxy tokens and the exact HTTPS origin. Never send credentials or session files in chat. Install current security-supported Python 3.11+ and Node 22+ on Windows. Install Caddy from its official release and verify its checksum.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]" pip-audit
.\.venv\Scripts\python.exe -m pip_audit
npm.cmd --prefix app ci
npm.cmd --prefix app audit
npm.cmd --prefix app test
npm.cmd --prefix app run build
.\.venv\Scripts\python.exe scripts\hosting.py check
.\.venv\Scripts\python.exe scripts\hosting.py validate --mode tunnel
```

`hosting.py` reads the existing API host/port from `.env`, derives its upstream and gives Caddy only its required configuration. It never rewrites API settings or passes Telegram/SMTP/EarnKaro/Mongo credentials to Caddy. A `.env` process override still takes priority, matching existing behavior. `check` validates local configuration/static files; it is not a live-host security certification.

## 2. Start the private origin

Use separate terminals during staging, or dedicated nonadministrator Windows service accounts in production:

```powershell
.\.venv\Scripts\python.exe superdeal_phase2_full\api.py
.\.venv\Scripts\python.exe scripts\hosting.py serve --mode tunnel
.\.venv\Scripts\python.exe superdeal_local_live_worker.py --confirm-monitor
```

Do not run the legacy `superdeal-api`/`superdeal-worker` entry points for this Mongo deployment. Do not serve the repository with `python -m http.server`. Vite and `vite preview` are not public production servers. The static web root is only `app/dist`.

The tunnel origin is `http://127.0.0.1:8080` unless you explicitly set a different `SUPERDEAL_FRONTEND_PORT`. The API port remains whatever your existing `.env` configures. The proxy allows all three POST alert routes, preserves `/go` affiliate redirects and blocks public admin/private-file routes. Admin diagnostics remain token-protected on the loopback API only.

## 3. Connect domain and HTTPS

1. Purchase the domain through GoDaddy; note existing DNS/email records before changing nameservers.
2. Add the domain to Cloudflare, review/import those records, then set GoDaddy's nameservers to the exact pair Cloudflare supplies. This does not transfer the domain registration.
3. Create a remotely managed Cloudflare Tunnel. Install its Windows connector using the dashboard's instructions. Treat its connector token as a secret.
4. Publish your chosen hostname to `http://127.0.0.1:8080` (or the configured frontend port). Do not publish the API, MongoDB, Ollama, filesystem or admin routes separately.
5. Verify the edge certificate and HTTPS redirect. Configure per-client edge throttling for alert submissions and abusive traffic. Do not cache `/deals*`, `/api/*`, `/go/*` or `/health`.
6. Leave router port forwarding disabled for this tunnel arrangement. Remove the temporary inbound test rule on 5175 and unnecessary Vite 5174 LAN rules after LAN testing is finished. Do not disable Windows Firewall.

The tunnel proxy trusts CF-Connecting-IP only on its loopback listener. Caddy overwrites the API's signed identity headers. The API accepts a forwarded identity only from authenticated loopback Caddy, so visitors do not all share one alert quota. Never expose that HTTP listener to other interfaces.

`deploy/Caddyfile` is an alternative direct-TLS configuration, requiring public reachability on 80/443 and an appropriate host/network design. `hosting.py ... --mode direct` validates/serves it. Use one entry point, not both on conflicting ports.

## 4. Required machine controls before public launch

- Enable MongoDB authentication, bind it privately and use a non-admin application identity. `mongo-api-role.js` prepares a collection-scoped public API role without creating passwords/users. The API now initializes only public alert/click indexes, not worker collections. Give the API service its own MONGODB_URI through its private process environment; keep worker credentials separate. Verify unauthorized Mongo access is denied from another device.
- Deny external access to MongoDB, API, Ollama, Caddy administration and Vite. The tunnel Caddy admin API is disabled.
- Run merchant scraping in a worker network/sandbox that cannot reach loopback, LAN/private ranges, link-local or metadata endpoints. Existing URL/DNS checks and request interception are defense in depth, not a DNS-rebinding-proof isolation boundary. Verify the restriction from that worker environment; do not claim that a configuration flag proves isolation.
- Configure authenticated STARTTLS SMTP and a real sender locally before public Get Notified testing. Dry-run previews are private, not delivered emails. Test email confirmation, quota and stop links with your own address.
- Set PC sleep/reboot/network recovery policies. Configure Windows Task Scheduler/service supervision for API, Caddy, tunnel connector, Telegram runner and notification worker. Use full paths, the repository working directory and least-privilege accounts. Perform a cold-reboot test; avoid duplicate Telegram sessions.
- Restrict ACLs for `.env`, Telegram sessions, raw/inbox data, dry-run emails, logs, backups and Caddy's data folder. Do not place them in `app/dist` or a public share.
- Create authenticated Mongo backups and perform a restore into a disposable database before launch. Test that the restored data contains publication/alert indexes and Telegram checkpoints. Do not modify or replay historical published deals.

## 5. Final public-host acceptance

From a separate device/network:

```powershell
.\.venv\Scripts\python.exe scripts\check_public_security.py https://YOUR-DOMAIN
```

Then test real browser behavior under CSP, image loading, search/filter/pagination, exact Shop links, alert signup/confirmation/unsubscribe, Telegram raw capture and worker publication. Inspect actual firewall exposure, TLS certificate, edge limits and recovery after restart. Do not call the site production-cleared until these machine/domain checks pass.

References: https://www.godaddy.com/en-in/help/change-my-domain-nameservers-664 ; https://developers.cloudflare.com/tunnel/get-started/ ; https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/as-a-service/windows/ ; https://caddyserver.com/docs/caddyfile/directives/reverse_proxy ; https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
