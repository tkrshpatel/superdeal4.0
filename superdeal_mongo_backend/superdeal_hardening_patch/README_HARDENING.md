# SuperDeal isolated backend hardening patch

This package replaces only `backend.py` in the standalone `superdeal_mongo_backend` prototype and adds `test_hardening.py`. **Do not copy into `src/superdeal` or switch the existing app.**

Before applying, back up the prototype `backend.py` or extract into a separate directory. Copy both files alongside `prompt.py`, `api.py`, and the existing tests.

```powershell
cd C:\Users\Home\superdeal3.0
.\.venv\Scripts\Activate.ps1
python -m pytest superdeal_mongo_backend\test_hardening.py -v
python -m pytest superdeal_mongo_backend\test_backend.py superdeal_mongo_backend\test_mongodb_integration.py superdeal_mongo_backend\test_api.py superdeal_mongo_backend\test_http_mongodb_e2e.py -v
```

Test databases are named `superdeal_test_hardening_<random>` and are deleted in teardown. No Telegram or EarnKaro calls are made; the LLM is mocked. The previous live Mistral suite can be run separately.

## What this addresses
- Explicit `fail_interrupted_jobs()` maintenance operation: marks PROCESSING records FAILED; does not retry them. **Do not invoke while active workers are processing.**
- Publication status update must actually succeed.
- Publication API gate refuses a published batch when the count or sequential indexes do not match.
- stderr fallback when database audit log insert fails.

## Still outstanding before production
- A real transaction or equivalent robust multi-document publication protocol, plus tests for connection loss at each write boundary.
- Persistent structured fallback log file with rotation, alerting, and redaction of sensitive errors.
- Admin API authorization and redaction audit; currently admin endpoints can expose raw error text/tracebacks.
- Cross-process concurrency controls, startup/shutdown and DB disconnect behavior.
- GitHub branch/CI verification for Tests, Mobile App and Android App CI; no merge.

These tests cannot certify production readiness. The current MongoDB standalone approach uses a read-side visibility gate, not a true multi-document transaction.
