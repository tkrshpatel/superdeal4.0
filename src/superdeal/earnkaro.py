"""EarnKaro batch conversion for whole Telegram messages."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

from .database import connect, upsert_deal
from .parser import duplicate_hash, parse_deal

LOGGER = logging.getLogger("superdeal.earnkaro")

API_URL = "https://ekaro-api.affiliaters.in/api/converter/public"


class EarnKaroError(RuntimeError):
    """Raised when EarnKaro conversion cannot be completed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def convert_message_via_api(message: str, api_key: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Send the entire original Telegram message to EarnKaro as one request.

    No URLs are extracted or transformed before this call.
    """
    payload = {"deal": message, "convert_option": "convert_only"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise EarnKaroError(f"request failed: {exc}") from exc

    if response.status_code != 200:
        raise EarnKaroError(
            f"HTTP {response.status_code}: {response.text[:1000]}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise EarnKaroError("EarnKaro returned non-JSON response") from exc

    converted = body.get("data")
    if not isinstance(converted, str) or not converted.strip():
        raise EarnKaroError("EarnKaro returned no converted message")

    if "we could not find" in converted.lower():
        raise EarnKaroError(converted)

    return {
        "response_text": converted.strip(),
        "response_payload": body,
    }


def queue_unique_telegram_messages(connection, *, limit: int = 100) -> int:
    """Create idempotent EarnKaro jobs for canonical Telegram messages only."""
    now = _now()
    rows = connection.execute(
        """SELECT r.id, r.source_channel, r.source_message_id, r.raw_text
           FROM telegram_raw_messages AS r
           LEFT JOIN earnkaro_conversions AS e
             ON e.telegram_raw_message_id = r.id
           WHERE r.is_duplicate = 0
             AND e.id IS NULL
           ORDER BY r.id
           LIMIT ?""",
        (limit,),
    ).fetchall()

    for row in rows:
        connection.execute(
            """INSERT OR IGNORE INTO earnkaro_conversions
               (telegram_raw_message_id, source_channel, source_message_id,
                request_text, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (
                row["id"],
                row["source_channel"],
                row["source_message_id"],
                row["raw_text"],
                now,
                now,
            ),
        )
    connection.commit()
    return len(rows)


def process_pending_earnkaro(
    connection,
    *,
    api_key: str | None = None,
    limit: int = 10,
) -> int:
    """Convert pending/failed jobs, one whole Telegram message per request."""
    key = (api_key if api_key is not None else os.getenv("API_KEY_EARNKARO", "")).strip()
    if not key:
        LOGGER.info("API_KEY_EARNKARO not configured; EarnKaro processing skipped")
        return 0

    rows = connection.execute(
        """SELECT *
           FROM earnkaro_conversions
           WHERE status IN ('pending', 'error')
           ORDER BY id
           LIMIT ?""",
        (limit,),
    ).fetchall()

    processed = 0
    for row in rows:
        attempts = int(row["attempts"]) + 1
        started = _now()
        connection.execute(
            """UPDATE earnkaro_conversions
               SET status = 'processing', attempts = ?, updated_at = ?, last_error = NULL
               WHERE id = ?""",
            (attempts, started, row["id"]),
        )
        connection.commit()

        try:
            result = convert_message_via_api(row["request_text"], key)
        except EarnKaroError as exc:
            connection.execute(
                """UPDATE earnkaro_conversions
                   SET status = 'error', last_error = ?, updated_at = ?
                   WHERE id = ?""",
                (str(exc), _now(), row["id"]),
            )
            connection.commit()
            LOGGER.warning(
                "EarnKaro conversion failed: channel=%s message_id=%s error=%s",
                row["source_channel"], row["source_message_id"], exc,
            )
            processed += 1
            continue

        body = result["response_payload"]
        provider_reference = None
        if isinstance(body, dict):
            for field in ("reference", "reference_id", "id", "request_id"):
                value = body.get(field)
                if value is not None:
                    provider_reference = str(value)
                    break

        connection.execute(
            """UPDATE earnkaro_conversions
               SET status = 'converted',
                   provider_reference = ?,
                   response_text = ?,
                   response_payload = ?,
                   updated_at = ?,
                   last_error = NULL
               WHERE id = ?""",
            (
                provider_reference,
                result["response_text"],
                json.dumps(body, ensure_ascii=False),
                _now(),
                row["id"],
            ),
        )
        connection.commit()

        # The successful EarnKaro response is the canonical source for every
        # downstream deal field. Original Telegram raw_text is never parsed
        # into deals or exposed to downstream consumers.
        converted_text = result["response_text"]
        deal = parse_deal(
            converted_text,
            source_channel=row["source_channel"],
            source_message_id=row["source_message_id"],
        )
        upsert_deal(
            connection,
            duplicate_hash=duplicate_hash(deal),
            product_name=deal.product_name,
            deal_price=deal.deal_price,
            merchant=deal.merchant,
            source_url=deal.source_url,
            affiliate_url=deal.source_url,
            raw_text=converted_text,
            observed_at=_now(),
            source_channel=row["source_channel"],
            source_message_id=row["source_message_id"],
        )

        processed += 1
        LOGGER.info(
            "EarnKaro conversion completed and deal persisted: channel=%s message_id=%s",
            row["source_channel"], row["source_message_id"],
        )

    return processed
