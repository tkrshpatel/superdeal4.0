# SuperDeal MongoDB backend (isolated prototype)

This is a **separate, opt-in backend prototype**. It does not start Telegram monitoring, expose an API, change the existing application, or migrate SQLite data.

## Setup

```powershell
cd C:\Users\Home\superdeal3.0
.\.venv\Scripts\Activate.ps1
pip install pymongo requests pytest
# Copy backend.py and prompt.py into the same new folder, e.g. mongo_backend
python -m pytest mongo_backend\test_backend.py -v
```

To initialize MongoDB indexes without starting monitoring:

```powershell
cd mongo_backend
python -c "from backend import connect; connect().setup(); print('MongoDB indexes ready')"
```

`Backend.ingest(channel, message_id, text)` inserts one message and PENDING status. `Backend.process(raw_id)` is **explicitly invoked**, never scheduled. It calls EarnKaro then Mistral; do not call it until you want to test with actual external services. Pass `converter` and `llm` test doubles for offline testing. `Backend.published_offers()` gates visibility on PUBLISHED status and matching publication ID.

**Limitations before production:** This is a first implementation, not a production-ready replacement. It needs an HTTP API, more integration tests against local MongoDB, robust crash recovery marking stranded PROCESSING jobs FAILED without retrying, startup/worker fault logs, and verified atomic publication on a MongoDB deployment supporting transactions. Current publication uses an eligibility gate so staged records are hidden before status publication; it does not provide a multi-document transaction. Do not connect web/mobile or enable monitoring yet.
