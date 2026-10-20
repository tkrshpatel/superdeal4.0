"""Deal freshness and expiry helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _current(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)


def freshness_status(last_seen_at: str, *, now: datetime | None = None,
                     stale_after: timedelta = timedelta(hours=24)) -> str:
    current = _current(now)
    observed = _parse_timestamp(last_seen_at)
    age = current - observed
    if age.total_seconds() < 0:
        return "future"
    return "fresh" if age <= stale_after else "stale"


def mark_stale_deals(connection: sqlite3.Connection, *, now: datetime | None = None,
                     stale_after: timedelta = timedelta(hours=24)) -> int:
    current = _current(now)
    cutoff_iso = (current - stale_after).isoformat().replace("+00:00", "Z")
    cursor = connection.execute(
        """UPDATE deals SET status = 'stale'
           WHERE status = 'active' AND last_seen_at < ?""",
        (cutoff_iso,),
    )
    connection.commit()
    return cursor.rowcount


def expire_stale_deals(connection: sqlite3.Connection, *, now: datetime | None = None,
                       stale_after: timedelta = timedelta(hours=24),
                       expire_after: timedelta = timedelta(days=7)) -> int:
    current = _current(now)
    cutoff_iso = (current - expire_after).isoformat().replace("+00:00", "Z")
    cursor = connection.execute(
        """UPDATE deals SET status = 'expired'
           WHERE status IN ('active', 'stale') AND last_seen_at < ?""",
        (cutoff_iso,),
    )
    connection.commit()
    return cursor.rowcount


def deal_freshness(connection: sqlite3.Connection, deal_id: int, *,
                   now: datetime | None = None,
                   stale_after: timedelta = timedelta(hours=24),
                   expire_after: timedelta = timedelta(days=7)) -> dict | None:
    row = connection.execute(
        "SELECT id, status, last_seen_at FROM deals WHERE id = ?", (deal_id,)
    ).fetchone()
    if row is None:
        return None

    current = _current(now)
    observed = _parse_timestamp(row["last_seen_at"])
    age_seconds = max(0.0, (current - observed).total_seconds())
    if age_seconds < 0:
        status = "future"
    elif age_seconds > expire_after.total_seconds():
        status = "expired"
    elif age_seconds > stale_after.total_seconds():
        status = "stale"
    else:
        status = "fresh"

    return {
        "deal_id": deal_id,
        "status": status,
        "last_seen_at": row["last_seen_at"],
        "age_hours": round(age_seconds / 3600, 2),
        "stale_after_hours": round(stale_after.total_seconds() / 3600, 2),
        "expire_after_hours": round(expire_after.total_seconds() / 3600, 2),
    }
