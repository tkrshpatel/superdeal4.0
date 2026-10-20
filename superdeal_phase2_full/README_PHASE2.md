# SuperDeal MongoDB Backend — Phase 2 consolidated test package

This is a standalone **development prototype**; do not overwrite the existing website or production backend. No Telegram monitoring is implemented or started.

## Installation (Windows PowerShell)

Extract this folder to `C:\Users\Home\superdeal3.0\superdeal_phase2_full`.

```powershell
cd C:\Users\Home\superdeal3.0
.\.venv\Scripts\Activate.ps1
pip install -r .\superdeal_phase2_full\requirements.txt
python -m pytest .\superdeal_phase2_full\test_backend.py .\superdeal_phase2_full\test_mongodb_integration.py .\superdeal_phase2_full\test_api.py .\superdeal_phase2_full\test_http_mongodb_e2e.py .\superdeal_phase2_full\test_hardening.py .\superdeal_phase2_full\test_phase2.py -v
```

For live local Mistral tests (requires running Ollama with `mistral:instruct`):

```powershell
$env:OLLAMA_MODEL = 'mistral:instruct'
python -m pytest .\superdeal_phase2_full\test_mistral_live.py -v -s
```

**Safety:** Integration tests create randomly named `superdeal_test_*` databases and drop only those. Do not run them against an untrusted MongoDB URI. No Telegram or EarnKaro requests are made by tests. The Mistral test makes requests only to local Ollama.

## Phase 2 changes

- Atomic `PENDING → PROCESSING` claim for concurrent workers; unique-index duplicate ingestion guard.
- Failed jobs cannot be retried automatically; recovery marks interrupted jobs FAILED.
- MongoDB audit logging fallback to append-only JSONL file (`SUPERDEAL_FALLBACK_LOG`, default `data/superdeal_fallback_errors.jsonl`). Sensitive error details excluded from fallback.
- Admin API output restricted to explicit safe fields; startup requires `SUPERDEAL_ADMIN_TOKEN` and loopback bind unless explicitly overridden.
- Published-deal reads validate complete offer-index sequence before exposing any item.

## Important limitations / release blockers

- MongoDB standalone does **not** support multi-document transactions. Publication currently uses a visibility gate and integrity checks, not a transactional commit. Under concurrent mutations, it is not a strict snapshot guarantee.
- The API reads all published statuses for each list/detail request; this is not yet scalable or optimized for production.
- No TLS, user auth, rate limiting, public deployment or production process supervision are included. Do not expose directly to the internet.
- No fully automated operational alerting or guarantee that errors are durably logged if both MongoDB and local disk are unavailable.
- No CI workflow has been run for this bundle; no GitHub merge or app switch is authorized.
- Previous test files are bundled for regression; all must be rerun against the consolidated code on your Windows PC.
