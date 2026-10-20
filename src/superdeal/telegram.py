"""Telegram ingestion adapters for SuperDeal 3.0."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("superdeal.telegram")


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    channel: str
    message_id: str
    text: str
    observed_at: str


class TelegramSource(Protocol):
    def fetch_messages(self, channel: str, *, limit: int = 100) -> Iterable[TelegramMessage]:
        ...

    def fetch_messages_for_channels(
        self, channels: Iterable[str], *, limit: int = 100
    ) -> dict[str, list[TelegramMessage]]:
        ...


class MockTelegramSource:
    """Deterministic source used by tests and local development."""

    def __init__(self, messages: Iterable[TelegramMessage] = ()) -> None:
        self._messages = list(messages)

    def fetch_messages(self, channel: str, *, limit: int = 100) -> list[TelegramMessage]:
        if limit < 1:
            return []
        return [message for message in self._messages if message.channel == channel][:limit]

    def fetch_messages_for_channels(
        self, channels: Iterable[str], *, limit: int = 100
    ) -> dict[str, list[TelegramMessage]]:
        return {channel: self.fetch_messages(channel, limit=limit) for channel in channels}


class TelegramAPIError(RuntimeError):
    """Raised when Telegram returns an unsuccessful Bot API response."""


def _normalize_channel_config(channel: str) -> str:
    """Normalize a configured Telegram channel identifier.

    Supported identifiers are numeric chat IDs, @public usernames, or plain
    usernames. Invite-link tokens are intentionally not treated as usernames.
    """
    value = channel.strip()
    if not value:
        return value
    if value.startswith("@"):
        return value[1:].lower()
    return value.lower()


def _chat_matches_config(chat: dict, configured: str) -> bool:
    """Return whether a Telegram chat matches a configured identifier."""
    value = configured.strip()
    normalized = _normalize_channel_config(value)
    chat_id = str(chat.get("id", "")).strip()
    username = str(chat.get("username", "")).strip().lstrip("@").lower()
    title = " ".join(str(chat.get("title", "")).split()).lower()

    if not normalized:
        return False

    # Numeric Telegram chat IDs are the most reliable identifier.
    if normalized.lstrip("-").isdigit():
        return normalized == chat_id

    # Telegram public usernames are optional; private channels normally have
    # no username, so a username configuration cannot match them.
    if normalized.startswith("+"):
        return False

    normalized_text = " ".join(normalized.split())
    return normalized_text == username or normalized_text == title


class TelegramBotSource:
    """Read channel posts through Telegram Bot API long polling."""

    def __init__(self, token: str, *, timeout: int = 25, request: Callable[[str, dict], dict] | None = None) -> None:
        if not token.strip():
            raise ValueError("Telegram bot token is required")
        if timeout < 1:
            raise ValueError("timeout must be positive")
        self.token = token.strip()
        self.timeout = timeout
        self._request = request or self._http_request
        self._offset = 0

    def _http_request(self, method: str, params: dict) -> dict:
        query = urlencode(params)
        url = f"https://api.telegram.org/bot{self.token}/{method}?{query}"
        request = Request(url, headers={"User-Agent": "SuperDealBot/1.0"})
        with urlopen(request, timeout=self.timeout + 5) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_me(self) -> dict:
        return self._call("getMe", {})

    def fetch_updates(self, *, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        updates = self._call(
            "getUpdates",
            {
                "offset": self._offset or None,
                "limit": limit,
                "timeout": self.timeout,
                "allowed_updates": json.dumps(["channel_post", "edited_channel_post"]),
            },
        )
        if updates:
            self._offset = max(int(item["update_id"]) for item in updates) + 1
        return updates

    def _messages_from_updates(
        self, updates: Iterable[dict], channels: Iterable[str], limit: int
    ) -> dict[str, list[TelegramMessage]]:
        configured = tuple(channels)
        result = {channel: [] for channel in configured}
        matched_update_ids: set[int] = set()

        for update in updates:
            payload = update.get("channel_post") or update.get("edited_channel_post")
            if not payload:
                continue

            chat = payload.get("chat") or {}
            matched_channels = [
                channel for channel in configured if _chat_matches_config(chat, channel)
            ]

            if not matched_channels:
                LOGGER.warning(
                    "Ignoring Telegram update %s from unconfigured channel: id=%s title=%r username=%r",
                    update.get("update_id"),
                    chat.get("id"),
                    chat.get("title"),
                    chat.get("username"),
                )
                continue

            matched_update_ids.add(int(update["update_id"]))
            timestamp = datetime.fromtimestamp(
                int(payload["date"]), tz=timezone.utc
            ).isoformat()
            text = payload.get("text") or payload.get("caption") or ""
            message_id = str(payload["message_id"])

            for channel in matched_channels:
                if len(result[channel]) < limit:
                    result[channel].append(
                        TelegramMessage(
                            channel=channel,
                            message_id=message_id,
                            text=str(text),
                            observed_at=timestamp,
                        )
                    )

        if updates:
            total = len(tuple(updates)) if not isinstance(updates, list) else len(updates)
            LOGGER.debug(
                "Telegram routing matched %d/%d update(s)",
                len(matched_update_ids),
                total,
            )
        return result

    def fetch_messages_for_channels(
        self, channels: Iterable[str], *, limit: int = 100
    ) -> dict[str, list[TelegramMessage]]:
        configured = tuple(channels)
        if limit < 1:
            return {channel: [] for channel in configured}
        updates = self.fetch_updates(limit=min(limit * max(len(configured), 1), 100))
        return self._messages_from_updates(updates, configured, limit)

    def fetch_messages(self, channel: str, *, limit: int = 100) -> list[TelegramMessage]:
        return self.fetch_messages_for_channels((channel,), limit=limit).get(channel, [])


    def close(self) -> None:
        """Close the Bot API source.

        Bot API polling uses stateless HTTP requests, so there is no persistent
        client connection to close. The method exists so bot and user readers
        can share the same worker lifecycle contract.
        """
        return None

    def _call(self, method: str, params: dict) -> list | dict:
        cleaned = {key: value for key, value in params.items() if value is not None}
        payload = self._request(method, cleaned)
        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("description", f"Telegram {method} failed"))
        return payload.get("result", [])
