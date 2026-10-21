"""Controlled real MongoDB + Mistral experiment; NEVER publishes a deal.

Input: an exact link already returned by EarnKaro. Does not call EarnKaro.
Only inserts into dev DB playwright_raw, never raw/ek_raw/fact_table/status.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "superdeal_phase2_full"))

from pymongo import MongoClient, ASCENDING  # noqa: E402
from backend import Backend, urls  # noqa: E402
from pre_llm_research import (  # noqa: E402
    research_message, persist_research, load_research, llm_evidence
)


def main():
    parser = argparse.ArgumentParser(description="Test Playwright -> MongoDB -> Mistral without publication")
    parser.add_argument("--url", required=True, help="Exact, already-converted EarnKaro URL")
    parser.add_argument("--database", default="superdeal_dev4", help="Isolated test DB (not 'superdeal')")
    args = parser.parse_args()
    if args.database == "superdeal" or not args.database.startswith("superdeal_dev"):
        parser.error("Only isolated superdeal_dev* databases are permitted.")
    if urls(args.url) != {args.url}:
        parser.error("Provide exactly one complete unmodified affiliate URL.")

    # A minimal converted-message fixture with no price deliberately tests
    # whether the merchant research price can be selected by Mistral.
    converted_text = "Product deal (price not supplied in message): " + args.url
    raw_id = "integration-test:" + uuid4().hex
    client = MongoClient(
        os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/?replicaSet=rs0"),
        serverSelectionTimeoutMS=5000,
    )
    try:
        client.admin.command("ping")
        collection = client[args.database].playwright_raw
        collection.create_index([("raw_id", ASCENDING), ("affiliate_url", ASCENDING)], unique=True)

        print("TEST RECORD:", raw_id)
        print("1. Extracting merchant research...")
        records = research_message(converted_text)
        print("RESEARCH:", json.dumps(records[args.url], ensure_ascii=False, indent=2))

        print("2. Saving research into MongoDB playwright_raw...")
        persist_research(collection, raw_id, converted_text, records)
        saved = load_research(collection, raw_id, converted_text)
        assert saved == records, "MongoDB research snapshot differs from scraped evidence"
        print("SAVED AND RELOADED: YES")

        print("3. Sending SAVED evidence plus the exact URL to local Mistral...")
        model_input = llm_evidence(converted_text, saved)
        llm_response = Backend._ollama(model_input)
        print("MISTRAL RAW JSON:", llm_response)

        print("4. Validating exact EarnKaro link and product schema...")
        # Show missing schema fields explicitly rather than masking them behind
        # a generic validation error. Keep Backend.validate strict.
        try:
            decoded = json.loads(llm_response)
            required = {"products", "unassigned_urls", "message_issues", "analysis_summary"}
            print("MODEL ROOT KEYS:", sorted(decoded) if isinstance(decoded, dict) else type(decoded).__name__)
            if isinstance(decoded, dict) and required - set(decoded):
                print("MISSING ROOT KEYS:", sorted(required - set(decoded)))
        except (ValueError, TypeError):
            print("MODEL JSON: INVALID")
        parsed = Backend.validate(llm_response, converted_text)
        for product in parsed["products"]:
            evidence = saved.get(product["affiliate_urls"][0], {})
            if product["deal_price"] is not None and evidence.get("price") is None:
                print("WARNING: LLM deal price has no Playwright price evidence.")
            if product["original_price"] is not None and evidence.get("mrp") is None:
                print("WARNING: LLM original price has no Playwright MRP evidence.")
        for product in parsed["products"]:
            print("PRODUCT:", product["product_name"])
            print("DEAL PRICE:", product["deal_price"])
            print("ORIGINAL PRICE:", product["original_price"])
            print("AFFILIATE URLS:", product["affiliate_urls"])
        print("PASS: Mistral output uses the exact input affiliate URL(s).")
        print("NO PUBLICATION: fact_table and pipeline_status were not touched.")
    except Exception as exc:
        print("INTEGRATION FAILED:", type(exc).__name__, str(exc)[:350], file=sys.stderr)
        print("NO PUBLICATION: this script never writes fact_table or pipeline_status.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        client.close()


if __name__ == "__main__":
    main()
