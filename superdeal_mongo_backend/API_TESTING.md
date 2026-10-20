# Isolated HTTP API test

This update adds `api.py` and `test_api.py` to the existing `superdeal_mongo_backend` folder. No Telegram listener, EarnKaro request, or Ollama request is started by the API.

## Windows tests

From `C:\Users\Home\superdeal3.0` with `.venv` active:

```powershell
python -m pytest superdeal_mongo_backend\test_api.py -v
```

Expected: 5 tests. These tests use an in-memory stub and exercise a real loopback HTTP server. They do not write MongoDB data.

## Optional real MongoDB HTTP smoke test

The following uses the `superdeal_test_api` database, not `superdeal`. Run in a separate PowerShell window:

```powershell
cd C:\Users\Home\superdeal3.0\superdeal_mongo_backend
$env:MONGODB_DATABASE = 'superdeal_test_api'
$env:SUPERDEAL_ADMIN_TOKEN = 'replace-with-a-long-random-local-test-token'
python api.py
```

Then in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:8765/api/v1/deals
Invoke-RestMethod http://127.0.0.1:8765/api/v1/admin/status -Headers @{Authorization='Bearer replace-with-a-long-random-local-test-token'}
```

Stop the API with Ctrl+C. By default it binds only to 127.0.0.1. No data ingestion occurs. Empty deals/status responses are expected for a fresh test database.

## Known limitations

- Prototype only; no production auth framework, rate limiting, HTTPS termination, or deployment configuration.
- The deal-detail lookup scans at most 10,001 eligible offers; a scalable indexed lookup is needed before launch.
- The underlying backend's `published_offers` performs a collection scan and needs pagination optimization.
- Crash recovery, robust logging fallback, and publication atomicity are not yet completed.
- Do not connect existing web/mobile apps or enable Telegram monitoring yet.
