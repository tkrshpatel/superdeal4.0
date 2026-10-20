"""One synthetic MongoDB publication for SuperDeal preview. No Telegram or EarnKaro network calls."""
import os
import sys
from pathlib import Path
from uuid import uuid4
from urllib.request import urlopen
import json

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "superdeal_phase2_full"))
from backend import connect

def main():
    backend = connect()
    backend.setup()
    run_id = uuid4().hex[:12]
    url = "https://example.com/superdeal-synthetic-" + run_id
    name = "SuperDeal Synthetic Preview " + run_id
    backend.converter = lambda _text: {
        "response_text": url,
        "response_payload": {"synthetic_test_only": True, "data": url},
    }
    backend.llm = lambda _response: {
        "products": [{
            "product_name": name,
            "brand": "SuperDeal",
            "ecommerce_platform": "Synthetic Test",
            "deal_price": 999,
            "original_price": None,
            "discount_percentage": None,
            "affiliate_urls": [url],
            "confidence": 100,
            "issues": [],
        }],
        "unassigned_urls": [],
        "message_issues": [],
        "analysis_summary": "Synthetic preview only",
    }
    raw_id = backend.ingest("@superdeal_synthetic_preview", run_id, "SYNTHETIC TEST ONLY " + url)
    count = backend.process(raw_id)
    if count != 1:
        raise RuntimeError("Expected exactly one published synthetic product")
    published = backend.legacy_search(q=run_id)["items"]
    if len(published) != 1:
        raise RuntimeError("Synthetic deal not visible in MongoDB backend")
    with urlopen("http://127.0.0.1:8765/deals?q=" + run_id, timeout=5) as response:
        payload = json.load(response)
    matches = payload.get("deals", [])
    if len(matches) != 1:
        raise RuntimeError("API did not return exactly one synthetic deal: " + repr(payload))
    print("PASS: Synthetic deal published transactionally and visible through MongoDB API")
    print("Deal name:", name)
    print("Deal ID:", matches[0]["id"])
    print("Open the web app and search:", run_id)
    print("Do not click the synthetic Buy button; the destination is example.com.")
    print("Telegram monitoring remains OFF; no real EarnKaro or LLM calls were made.")

if __name__ == "__main__":
    main()
