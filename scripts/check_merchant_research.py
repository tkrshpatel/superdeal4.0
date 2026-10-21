"""Read-only Playwright research comparison for real EarnKaro merchant links.

Example:
  python scripts/check_merchant_research.py https://amzn.to/... https://fkrt.cc/...
Does not use EarnKaro API, Mistral, Telegram, or MongoDB.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "superdeal_phase2_full"))

from pre_llm_research import research_message  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Compare live merchant metadata without publishing deals")
    parser.add_argument("links", nargs="+", help="Exact EarnKaro affiliate URLs to inspect")
    args = parser.parse_args()
    if len(args.links) > 12:
        parser.error("Provide at most 12 links per run.")
    for link in args.links:
        parsed = urlsplit(link)
        if parsed.scheme != "https" or not parsed.hostname:
            parser.error("Every link must be a complete HTTPS URL.")
    message = "\n".join(args.links)
    research = research_message(message, max_links=len(args.links))
    for link in args.links:
        item = research.get(link, {})
        print("\n" + "=" * 64)
        print("AFFILIATE URL (UNCHANGED):", link)
        print("STATUS:", item.get("status"))
        print("PRODUCT NAME:", item.get("product_name"))
        print("DESCRIPTION:", item.get("description"))
        print("BRAND:", item.get("brand"))
        print("PRICE:", item.get("price"), "SOURCE:", item.get("price_source"))
        print("MRP:", item.get("mrp"), "SOURCE:", item.get("mrp_source"))
        print("IMAGE:", item.get("image_url"))
    print("\nNote: FOUND means an image loaded, not that every field is verified.")


if __name__ == "__main__":
    main()
