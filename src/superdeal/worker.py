"""Continuous Telegram ingestion orchestration."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from .database import connect
from .earnkaro import process_pending_earnkaro, queue_unique_telegram_messages
from .ingest import ingest_messages
from .llm_enrichment import enrich_pending_deals_with_llm
from .llm_enrichment import enrich_pending_deals_with_llm
from .product_enrichment import enrich_pending_deals
from .telegram import TelegramBotSource, TelegramMessage
from .telegram_user import TelegramUserReaderError, TelegramUserSource

LOGGER = logging.getLogger("superdeal.worker")


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    token: str
    channels: tuple[str, ...]
    database_url: str = "data/superdeal.db"
    poll_interval: float = 1.0
    batch_limit: int = 100
    reader_mode: str = "bot"
    api_id: str = ""
    api_hash: str = ""
    session: str = "data/telegram_user"

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        channels = tuple(
            item.strip()
            for item in os.getenv("TELEGRAM_CHANNELS", "").split(",")
            if item.strip()
        )
        database_url = os.getenv("DATABASE_URL", "data/superdeal.db")
        poll_interval = float(os.getenv("TELEGRAM_POLL_INTERVAL", "1"))
        batch_limit = int(os.getenv("TELEGRAM_BATCH_LIMIT", "100"))
        reader_mode = os.getenv("TELEGRAM_READER_MODE", "bot").strip().lower()
        api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        session = os.getenv("TELEGRAM_SESSION", "data/telegram_user").strip()
        return cls(
            token, channels, database_url, poll_interval, batch_limit,
            reader_mode, api_id, api_hash, session
        )

    def validate(self) -> None:
        if self.reader_mode not in {"bot", "user", "hybrid"}:
            raise ValueError("TELEGRAM_READER_MODE must be 'bot', 'user', or 'hybrid'")
        if self.reader_mode in {"bot", "hybrid"} and not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required in bot or hybrid reader mode")
        if self.reader_mode in {"user", "hybrid"}:
            if not self.api_id:
                raise ValueError("TELEGRAM_API_ID is required in user or hybrid reader mode")
            if not self.api_hash:
                raise ValueError("TELEGRAM_API_HASH is required in user or hybrid reader mode")
        if not self.channels:
            raise ValueError("TELEGRAM_CHANNELS must contain at least one channel")
        if self.poll_interval < 0:
            raise ValueError("TELEGRAM_POLL_INTERVAL must be non-negative")
        if not 1 <= self.batch_limit <= 100:
            raise ValueError("TELEGRAM_BATCH_LIMIT must be between 1 and 100")


def build_source(config: WorkerConfig):
    if config.reader_mode == "user":
        return TelegramUserSource(config.api_id, config.api_hash, session=config.session)
    if config.reader_mode == "hybrid":
        return (
            TelegramBotSource(config.token),
            TelegramUserSource(config.api_id, config.api_hash, session=config.session),
        )
    return TelegramBotSource(config.token)


def _merge_messages(
    configured: tuple[str, ...],
    primary: dict[str, list],
    fallback: dict[str, list],
) -> dict[str, list]:
    merged = {channel: list(primary.get(channel, [])) for channel in configured}
    seen = {
        (channel, message.message_id)
        for channel in configured
        for message in merged[channel]
    }
    for channel in configured:
        for message in fallback.get(channel, []):
            key = (channel, message.message_id)
            if key not in seen:
                merged[channel].append(message)
                seen.add(key)
    return merged


def run_once(config: WorkerConfig, *, source=None) -> int:
    config.validate()
    connection = connect(config.database_url, check_same_thread=False)
    try:
        if config.reader_mode == "hybrid":
            bot, user = source if source is not None else build_source(config)
            primary = bot.fetch_messages_for_channels(
                config.channels, limit=config.batch_limit
            )
            received_bot = sum(len(messages) for messages in primary.values())
            LOGGER.info(
                "Telegram bot reader received %d message(s) across %d configured channel(s)",
                received_bot,
                len(config.channels),
            )
            try:
                fallback = user.fetch_messages_for_channels(
                    config.channels, limit=config.batch_limit
                )
            except TelegramUserReaderError:
                LOGGER.exception(
                    "Telegram user reader failed; bot messages will still be ingested"
                )
                fallback = {channel: [] for channel in config.channels}
            messages_by_channel = _merge_messages(
                config.channels, primary, fallback
            )
            received = sum(len(messages) for messages in messages_by_channel.values())
            LOGGER.info(
                "Telegram hybrid reader collected %d unique message(s) across %d configured channel(s)",
                received,
                len(config.channels),
            )
        else:
            telegram = source or build_source(config)
            messages_by_channel = telegram.fetch_messages_for_channels(
                config.channels, limit=config.batch_limit
            )
            received = sum(len(messages) for messages in messages_by_channel.values())
            LOGGER.info(
                "Telegram %s reader received %d message(s) across %d configured channel(s)",
                config.reader_mode,
                received,
                len(config.channels),
            )

        processed = sum(
            ingest_messages(connection, messages_by_channel.get(channel, []))
            for channel in config.channels
        )
        queued = queue_unique_telegram_messages(connection, limit=config.batch_limit)
        converted = process_pending_earnkaro(connection, limit=config.batch_limit)
        enriched = enrich_pending_deals(connection, limit=min(config.batch_limit, 10))
        llm_enriched = enrich_pending_deals_with_llm(
            connection, limit=min(config.batch_limit, 10)
        )
        LOGGER.info(
            "Telegram poll ingested %d raw message(s); queued %d EarnKaro job(s); processed %d EarnKaro job(s); enriched %d deal(s); LLM-enriched %d deal(s)",
            processed,
            queued,
            converted,
            enriched,
            llm_enriched,
        )
        return processed
    finally:
        connection.close()


def _ingest_stream_message(
    connection,
    message: TelegramMessage,
) -> None:
    processed = ingest_messages(connection, [message])
    LOGGER.info(
        "Telegram stream persisted %d raw message(s): channel=%s message_id=%s",
        processed,
        message.channel,
        message.message_id,
    )


def _run_user_stream(config: WorkerConfig, source=None, stop_event=None) -> None:
    telegram = source or TelegramUserSource(
        config.api_id, config.api_hash, session=config.session
    )
    connection = connect(config.database_url, check_same_thread=False)
    try:
        LOGGER.info(
            "Starting Telethon live stream for %d configured channel(s)",
            len(config.channels),
        )
        telegram.run_forever(
            config.channels,
            lambda message: _ingest_stream_message(connection, message),
        )
    except Exception:
        if not stop_event or not stop_event.is_set():
            LOGGER.exception("Telegram user stream stopped unexpectedly")
            raise
    finally:
        connection.close()
        if source is None:
            telegram.close()


def _close_source(source) -> None:
    if isinstance(source, tuple):
        for item in source:
            close = getattr(item, "close", None)
            if close:
                close()
        return
    close = getattr(source, "close", None)
    if close:
        close()


def run_forever(
    config: WorkerConfig,
    *,
    source=None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    config.validate()

    # User mode follows the proven Telethon event-stream pattern directly.
    if config.reader_mode == "user":
        _run_user_stream(config, source=source)
        return

    # Hybrid mode keeps Bot API polling for bot-accessible channels while a
    # dedicated Telethon event loop handles channels the bot cannot access.
    if config.reader_mode == "hybrid":
        stop_event = threading.Event()
        if source is None:
            bot = TelegramBotSource(config.token)
            user_source = None
        else:
            bot, user_source = source

        user_holder: dict[str, TelegramUserSource] = {}
        user_failed = threading.Event()

        def user_runner() -> None:
            local_source = user_source
            if local_source is None:
                local_source = TelegramUserSource(
                    config.api_id, config.api_hash, session=config.session
                )
            user_holder["source"] = local_source
            try:
                _run_user_stream(config, source=local_source, stop_event=stop_event)
            except Exception:
                LOGGER.exception(
                    "Telegram user stream stopped; no channels are being monitored by the user reader"
                )
                user_failed.set()

        thread = threading.Thread(
            target=user_runner,
            name="superdeal-telegram-user",
            daemon=True,
        )
        thread.start()

        bot_config = replace(config, reader_mode="bot")
        # This derived config is scoped only to the Bot API polling call.
        # The runner's configured mode remains hybrid for its entire lifetime.
        try:
            while True:
                if user_failed.is_set():
                    raise TelegramUserReaderError(
                        "No Telegram channels are being monitored by the user reader; exiting hybrid runner"
                    )
                try:
                    run_once(bot_config, source=bot)
                except Exception:
                    LOGGER.exception("Telegram bot polling cycle failed; retrying")
                sleep(config.poll_interval)
        finally:
            stop_event.set()
            user_to_close = user_holder.get("source") or user_source
            if user_to_close:
                user_to_close.close()
            bot.close()
        return

    telegram = source or build_source(config)
    try:
        while True:
            try:
                run_once(config, source=telegram)
            except Exception:
                LOGGER.exception("Telegram polling cycle failed; retrying")
            sleep(config.poll_interval)
    finally:
        _close_source(telegram)
