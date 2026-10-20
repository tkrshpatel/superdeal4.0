# Phase 6 — Publication freshness and observed click counts

This remains an isolated MongoDB backend. No Telegram monitoring or production switch.

- Legacy `/deals` and `/deals/{id}` now derive `last_seen_at` from **published_at** (the publication timestamp, not merchant verification), `click_count` from `/go` events in the last 24 hours, and `hot` from >=5 recorded clicks.
- `fresh` means published within the last 24 hours. It does **not** verify current product price or stock.
- `/deals/{id}/price-history` returns HTTP 501 rather than inventing historical observations. A future observation collector and data model must be designed and tested separately.
- `popular` sorting remains unsupported; observed redirect clicks do not represent all historic traffic.
- `/go/{id}` returns an HTTP redirect to the exact EarnKaro URL. Android app-link routing is a mobile OS/client concern; **no Android implementation is included**.
- Tests use synthetic data and mocked conversion/LLM. Run them with MongoDB rs0. Existing website/mobile apps are untouched.

## Run

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/?replicaSet=rs0'
python -m pytest .\superdeal_phase2_full\test_phase6.py -v
python -m pytest .\superdeal_phase2_full\ --ignore=.\superdeal_phase2_full\test_mistral_live.py -v
```

## Pending before switching

- Inspect and adapt actual frontend source and Android intent/app-link behavior.
- Test full web/mobile integration against synthetic published records.
- Decide whether click counts should be approximate/partial or captured from every client path.
- Design price observation and history separately; Telegram advertised MRP is not historical verified price.
- Review authentication, TLS, deployment, error alerts, and CI workflows.
