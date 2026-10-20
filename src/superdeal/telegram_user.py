"""Telegram MTProto user-account reader for reliable channel streaming."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .telegram import TelegramMessage

LOGGER = logging.getLogger("superdeal.telegram_user")

PUBLIC_URL_RE = re.compile(
    r"^https?://(?:t\.me|telegram\.me)/(?:s/)?([^/?#]+)", re.I
)


class TelegramUserReaderError(RuntimeError):
    pass


def normalize_user_channel(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    match = PUBLIC_URL_RE.match(value)
    if match:
        value = match.group(1)
    if value.startswith("@"):
        value = value[1:]
    if value.startswith("+"):
        raise ValueError(
            "Invite-link tokens are not supported; use a public channel URL, "
            "username, or chat ID"
        )
    return value.strip()


class TelegramUserSource:
    """Authenticated Telegram user reader.

    The historical fetch API remains available for one-shot/testing use.
    Continuous ingestion uses Telethon's NewMessage event stream, matching
    the proven reference implementation while keeping TELEGRAM_CHANNELS as
    the explicit configuration boundary.
    """

    def __init__(
        self,
        api_id: int | str,
        api_hash: str,
        *,
        session: str = "data/telegram_user",
        client: Any | None = None,
    ) -> None:
        if not str(api_id).strip():
            raise ValueError("TELEGRAM_API_ID is required")
        if not api_hash.strip():
            raise ValueError("TELEGRAM_API_HASH is required")

        try:
            from telethon.sync import TelegramClient
        except ImportError as exc:
            raise TelegramUserReaderError(
                "Telethon is not installed. Install the project dependencies with: "
                "pip install -e ."
            ) from exc

        self.api_id = int(api_id)
        self.api_hash = api_hash.strip()
        self.session = session.strip() or "data/telegram_user"
        Path(self.session).parent.mkdir(parents=True, exist_ok=True)
        self.client = client or TelegramClient(
            self.session,
            self.api_id,
            self.api_hash,
            receive_updates=True,
            catch_up=False,
            sequential_updates=True,
        )
        if not self.client.is_connected():
            self.client.connect()
        if not self.client.is_user_authorized():
            self.client.disconnect()
            raise TelegramUserReaderError(
                "Telegram user session is not authorized. "
                "Run python -m superdeal.telegram_login once."
            )
        self._last_message_ids: dict[str, int] = {}

    def close(self) -> None:
        if self.client.is_connected():
            self.client.disconnect()

    def _resolve_entity(self, configured: str) -> Any:
        target = normalize_user_channel(configured)
        try:
            return self.client.get_entity(target)
        except (ValueError, TypeError) as exc:
            raise TelegramUserReaderError(
                f"Could not resolve Telegram channel {configured!r}. "
                "Use a public @username/URL, a known chat ID, or a channel "
                "visible to the account."
            ) from exc

    @staticmethod
    def _canonical_channel(entity: Any, configured: str) -> str:
        username = getattr(entity, "username", None)
        if username:
            return f"@{username}"
        title = " ".join(str(getattr(entity, "title", "")).split())
        return title or configured.strip()

    @staticmethod
    def message_from_event(event: Any, configured_channel: str | None = None) -> TelegramMessage | None:
        # Telethon events expose a Message in `.message`, whereas a raw
        # Telethon Message exposes its *text string* in `.message`.
        # Only unwrap an actual message-like object, never a string.
        candidate = getattr(event, "message", None)
        message = candidate if candidate is not None and not isinstance(candidate, (str, bytes)) and hasattr(candidate, "id") else event
        text = getattr(message, "raw_text", None) or getattr(message, "text", None) or ""
        if not str(text).strip():
            return None

        chat = getattr(event, "chat", None)
        username = getattr(chat, "username", None) if chat is not None else None
        title = " ".join(str(getattr(chat, "title", "")).split()) if chat is not None else ""
        channel = (
            f"@{username}"
            if username
            else title
            or configured_channel
            or str(getattr(event, "chat_id", "unknown"))
        )

        message_id = str(getattr(message, "id", 0) or 0)
        observed_at = getattr(message, "date", None) or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)

        return TelegramMessage(
            channel=channel,
            message_id=message_id,
            text=str(text),
            observed_at=observed_at.astimezone(timezone.utc).isoformat(),
        )

    def fetch_messages(self, channel: str, *, limit: int = 100) -> list[TelegramMessage]:
        return self.fetch_messages_for_channels((channel,), limit=limit).get(channel, [])

    def fetch_messages_for_channels(
        self, channels: Iterable[str], *, limit: int = 100
    ) -> dict[str, list[TelegramMessage]]:
        if limit < 1:
            return {channel: [] for channel in channels}

        configured = tuple(channels)
        result = {channel: [] for channel in configured}

        for channel in configured:
            entity = self._resolve_entity(channel)
            canonical = self._canonical_channel(entity, channel)
            last_id = self._last_message_ids.get(canonical, 0)
            messages = list(self.client.iter_messages(entity, limit=limit))
            fresh: list[TelegramMessage] = []

            for message in reversed(messages):
                message_id = int(getattr(message, "id", 0) or 0)
                if message_id <= last_id:
                    continue
                converted = self.message_from_event(message, canonical)
                if converted:
                    fresh.append(converted)

            if messages:
                newest_id = max(int(getattr(message, "id", 0) or 0) for message in messages)
                self._last_message_ids[canonical] = max(last_id, newest_id)

            result[channel].extend(fresh)

        return result

    def run_forever(
        self,
        channels: Iterable[str],
        on_message: Callable[[TelegramMessage], None],
    ) -> None:
        """Stream new channel messages until Telegram disconnects."""

        configured = tuple(channels)
        if not configured:
            raise ValueError("At least one Telegram channel is required")

        try:
            from telethon import events
        except ImportError as exc:
            raise TelegramUserReaderError("Telethon is not installed") from exc

        resolved: list[tuple[Any, str]] = []
        for channel in configured:
            try:
                entity = self._resolve_entity(channel)
            except TelegramUserReaderError:
                LOGGER.exception(
                    "Skipping unavailable Telegram channel in user stream: %s",
                    channel,
                )
                continue
            resolved.append((entity, channel))

        entities = [entity for entity, _ in resolved]
        canonical_by_id = {
            int(getattr(entity, "id", 0)): self._canonical_channel(entity, channel)
            for entity, channel in resolved
        }

        if not entities:
            raise TelegramUserReaderError(
                "No Telegram channels are being monitored: none of the configured channels could be resolved"
            )

        async def persist_message(message: Any, canonical: str | None) -> None:
            converted = self.message_from_event(message, canonical)
            if converted is None:
                return
            try:
                on_message(converted)
            except Exception:
                # Keep the Telegram event loop alive; the caller's logging
                # wrapper is responsible for surfacing persistence failures.
                LOGGER.exception("Telegram user message handler failed")

        async def handler(event: Any) -> None:
            chat_id = int(getattr(event, "chat_id", 0) or 0)
            canonical = canonical_by_id.get(chat_id)
            message = getattr(event, "message", event)
            event_date = getattr(message, "date", None) or datetime.now(timezone.utc)
            if event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=timezone.utc)
            event_date = event_date.astimezone(timezone.utc)
            cutoff = event_date - timedelta(minutes=15)

            entity = next(
                (
                    candidate
                    for candidate in entities
                    if int(getattr(candidate, "id", 0) or 0) == chat_id
                ),
                None,
            )
            if entity is not None:
                recent = self.client.iter_messages(
                    entity,
                    limit=None,
                    offset_date=event_date,
                )
                qualifying: list[Any] = []

                def is_in_window(candidate: Any) -> bool:
                    candidate_date = getattr(candidate, "date", None)
                    if candidate_date is None:
                        return False
                    if candidate_date.tzinfo is None:
                        candidate_date = candidate_date.replace(tzinfo=timezone.utc)
                    return candidate_date.astimezone(timezone.utc) >= cutoff

                if hasattr(recent, "__aiter__"):
                    async for candidate in recent:
                        if not is_in_window(candidate):
                            break
                        qualifying.append(candidate)
                else:
                    for candidate in recent:
                        if not is_in_window(candidate):
                            break
                        qualifying.append(candidate)

                for candidate in reversed(qualifying):
                    await persist_message(candidate, canonical)

            # offset_date returns messages before the triggering event, so persist
            # the live event itself after reconciling the preceding 15 minutes.
            await persist_message(event, canonical)

        event_filter = events.NewMessage(chats=entities)
        self.client.add_event_handler(handler, event_filter)

        try:
            self.client.run_until_disconnected()
        finally:
            self.client.remove_event_handler(handler, event_filter)
