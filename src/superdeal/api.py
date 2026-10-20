"""Small dependency-free HTTP API for SuperDeal 3.0."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .enrichment import enrich_deal
from .freshness import deal_freshness
from .intelligence import get_price_history, price_intelligence
from .parser import parse_deal


FRESH_WINDOW_HOURS = 24


def _cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=FRESH_WINDOW_HOURS)).isoformat()


def _with_enrichment(row: dict) -> dict:
    enriched = enrich_deal(parse_deal(row.get("raw_text", "")))
    row["discount_pct"] = enriched.discount_pct
    row["return_days"] = enriched.return_days
    row["has_coupon"] = enriched.has_coupon
    row["has_card_offer"] = enriched.has_card_offer
    row["has_cod"] = enriched.has_cod
    row["category"] = enriched.category_hint
    return row


def _click_count(connection: sqlite3.Connection, deal_id: int) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM deal_clicks WHERE deal_id = ? AND clicked_at >= ?",
        (deal_id, _cutoff()),
    ).fetchone()
    return int(row["n"])


def list_deals(connection: sqlite3.Connection, *, q: str | None = None, merchant: str | None = None,
               min_price: int | None = None, max_price: int | None = None,
               sort: str = "newest", limit: int = 50) -> list[dict]:
    if min_price is not None and min_price < 0:
        raise ValueError("min_price must be non-negative")
    if max_price is not None and max_price < 0:
        raise ValueError("max_price must be non-negative")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("min_price cannot exceed max_price")
    limit = max(1, min(limit, 100))
    clauses = ["d.status = 'active'", "d.affiliate_url IS NOT NULL", "d.affiliate_url != ''", "d.last_seen_at >= ?"]
    params: list[object] = [_cutoff()]
    if q:
        clauses.append("(LOWER(d.product_name) LIKE ? OR LOWER(COALESCE(d.merchant, '')) LIKE ? OR LOWER(d.raw_text) LIKE ?)")
        needle = f"%{q.lower()}%"
        params.extend([needle, needle, needle])
    if merchant:
        clauses.append("LOWER(d.merchant) = ?")
        params.append(merchant.lower())
    if min_price is not None:
        clauses.append("d.current_price >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("d.current_price <= ?")
        params.append(max_price)

    order_by = {
        "newest": "d.last_seen_at DESC",
        "price_asc": "d.current_price ASC, d.last_seen_at DESC",
        "price_desc": "d.current_price DESC, d.last_seen_at DESC",
        "popular": "click_count DESC, d.last_seen_at DESC",
    }
    if sort not in order_by:
        raise ValueError("sort must be one of: newest, price_asc, price_desc, popular")

    rows = connection.execute(
        f"""SELECT d.id, d.product_name, d.merchant, d.current_price, d.affiliate_url,
                   d.page_title, d.canonical_url, d.image_url, d.verified_price, d.last_verified_at,
                  d.description, d.brand, d.mrp, d.enriched_merchant, d.page_discount_pct, d.enrichment_status,
                   d.raw_text, d.status, d.first_seen_at, d.last_seen_at,
                   COUNT(c.id) AS click_count
            FROM deals d
            LEFT JOIN deal_clicks c
              ON c.deal_id = d.id AND c.clicked_at >= ?
            WHERE {' AND '.join(clauses)}
            GROUP BY d.id
            ORDER BY {order_by[sort]} LIMIT ?""",
        (_cutoff(), *params, limit),
    ).fetchall()
    result = []
    for row in rows:
        item = _with_enrichment(dict(row))
        item["click_count"] = int(item.get("click_count") or 0)
        item["hot"] = item["click_count"] >= 5
        result.append(item)
    return result


def get_deal(connection: sqlite3.Connection, deal_id: int) -> dict | None:
    row = connection.execute(
        """SELECT d.id, d.product_name, d.merchant, d.current_price, d.affiliate_url,
                  d.page_title, d.canonical_url, d.image_url, d.verified_price, d.last_verified_at,
                  d.description, d.brand, d.mrp, d.enrichment_status,
                  d.raw_text, d.status, d.first_seen_at, d.last_seen_at,
                  COUNT(c.id) AS click_count
           FROM deals d
           LEFT JOIN deal_clicks c ON c.deal_id = d.id AND c.clicked_at >= ?
           WHERE d.id = ? AND d.affiliate_url IS NOT NULL AND d.affiliate_url != '' AND d.last_seen_at >= ?
           GROUP BY d.id""",
        (_cutoff(), deal_id, _cutoff()),
    ).fetchone()
    if not row:
        return None
    item = _with_enrichment(dict(row))
    item["click_count"] = int(item.get("click_count") or 0)
    item["hot"] = item["click_count"] >= 5
    return item


def record_click(connection: sqlite3.Connection, deal_id: int) -> str | None:
    row = connection.execute(
        "SELECT affiliate_url, status, last_seen_at FROM deals WHERE id = ?",
        (deal_id,),
    ).fetchone()
    if not row or row["status"] != "active":
        return None
    if row["last_seen_at"] < _cutoff():
        return None
    target = row["affiliate_url"]
    if not target:
        return None
    connection.execute(
        "INSERT INTO deal_clicks (deal_id, clicked_at) VALUES (?, ?)",
        (deal_id, datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()
    return str(target)


def make_handler(connection: sqlite3.Connection):
    class DealAPIHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: object, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json({"status": "ok", "service": "superdeal3"})
                return
            if parsed.path == "/deals":
                params = parse_qs(parsed.query)
                q = params.get("q", [None])[0]
                merchant = params.get("merchant", [None])[0]
                sort = params.get("sort", ["newest"])[0]
                try:
                    limit = int(params.get("limit", ["50"])[0])
                    min_price = int(params["min_price"][0]) if "min_price" in params else None
                    max_price = int(params["max_price"][0]) if "max_price" in params else None
                    deals = list_deals(
                        connection, q=q, merchant=merchant, min_price=min_price,
                        max_price=max_price, sort=sort, limit=limit,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, 400)
                    return
                self._send_json({"deals": deals, "fresh_window_hours": FRESH_WINDOW_HOURS})
                return
            if parsed.path.startswith("/deals/"):
                parts = parsed.path.strip("/").split("/")
                try:
                    deal_id = int(parts[1])
                except (ValueError, IndexError):
                    self._send_json({"error": "invalid deal id"}, 400)
                    return
                deal = get_deal(connection, deal_id)
                if deal is None:
                    self._send_json({"error": "deal not found or expired"}, 404)
                    return
                if len(parts) == 3 and parts[2] == "price-history":
                    self._send_json({"deal_id": deal_id, "history": get_price_history(connection, deal_id)})
                    return
                if len(parts) == 3 and parts[2] == "intelligence":
                    self._send_json(price_intelligence(connection, deal_id))
                    return
                if len(parts) == 3 and parts[2] == "freshness":
                    self._send_json(deal_freshness(connection, deal_id))
                    return
                if len(parts) != 2:
                    self._send_json({"error": "not found"}, 404)
                    return
                self._send_json(deal)
                return
            if parsed.path.startswith("/go/"):
                try:
                    deal_id = int(parsed.path.strip("/").split("/")[1])
                except (ValueError, IndexError):
                    self._send_json({"error": "invalid deal id"}, 400)
                    return
                target = record_click(connection, deal_id)
                if target is None:
                    self._send_json({"error": "deal not found or expired"}, 404)
                    return
                self.send_response(302)
                self.send_header("Location", target)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._send_json({"error": "not found"}, 404)

        def log_message(self, format: str, *args: object) -> None:
            return

    return DealAPIHandler


def serve(connection: sqlite3.Connection, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = HTTPServer((host, port), make_handler(connection))
    try:
        server.serve_forever()
    finally:
        server.server_close()
