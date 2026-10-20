"""Price-history and deal-intelligence helpers."""

from __future__ import annotations

import sqlite3


def get_price_history(connection: sqlite3.Connection, deal_id: int) -> list[dict]:
    rows = connection.execute(
        """SELECT price, observed_at
           FROM price_history
           WHERE deal_id = ?
           ORDER BY id ASC""",
        (deal_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def price_intelligence(connection: sqlite3.Connection, deal_id: int) -> dict | None:
    deal = connection.execute(
        "SELECT current_price FROM deals WHERE id = ?", (deal_id,)
    ).fetchone()
    if deal is None:
        return None

    history = get_price_history(connection, deal_id)
    if not history:
        return {
            "current_price": deal["current_price"],
            "lowest_price": None,
            "highest_price": None,
            "previous_price": None,
            "change_pct": None,
            "is_historical_low": False,
            "observations": 0,
        }

    prices = [int(item["price"]) for item in history]
    current = int(deal["current_price"]) if deal["current_price"] is not None else None
    previous = prices[-2] if len(prices) >= 2 else None
    change_pct = None
    if current is not None and previous not in (None, 0):
        change_pct = round(((current - previous) / previous) * 100, 2)

    return {
        "current_price": current,
        "lowest_price": min(prices),
        "highest_price": max(prices),
        "previous_price": previous,
        "change_pct": change_pct,
        "is_historical_low": current is not None and current == min(prices),
        "observations": len(history),
    }
