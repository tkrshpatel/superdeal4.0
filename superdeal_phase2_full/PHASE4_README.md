# Phase 4: optimized versioned MongoDB API (isolated)

Unzip into C:\Users\Home\superdeal3.0, replacing superdeal_phase2_full.

```powershell
cd C:\Users\Home\superdeal3.0
.\.venv\Scripts\Activate.ps1
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/?replicaSet=rs0'
python -m pytest .\superdeal_phase2_full\test_phase4.py -v
python -m pytest .\superdeal_phase2_full\test_backend.py .\superdeal_phase2_full\test_mongodb_integration.py .\superdeal_phase2_full\test_api.py .\superdeal_phase2_full\test_http_mongodb_e2e.py .\superdeal_phase2_full\test_hardening.py .\superdeal_phase2_full\test_phase2.py .\superdeal_phase2_full\test_transactions.py .\superdeal_phase2_full\test_phase4.py -v
$env:OLLAMA_MODEL = 'mistral:instruct'
python -m pytest .\superdeal_phase2_full\test_mistral_live.py -v -s
```

This package has NOT been verified against your local MongoDB or web/mobile app.
