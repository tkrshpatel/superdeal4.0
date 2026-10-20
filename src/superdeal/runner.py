"""Production-oriented entry points for the Telegram worker."""

from __future__ import annotations

import logging
import os
from typing import Callable

from .telegram import TelegramBotSource
from .worker import WorkerConfig, build_source, run_forever

LOGGER = logging.getLogger("superdeal.worker")


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def check_telegram(
    config: WorkerConfig,
    *,
    bot_factory: Callable[[str], TelegramBotSource] = TelegramBotSource,
) -> dict[str, object]:
    config.validate()
    if config.reader_mode == "user":
        source = build_source(config)
        try:
            me = source.client.get_me()
            return {
                "ok": True,
                "reader": "user",
                "account": getattr(me, "username", None) or getattr(me, "first_name", None),
            }
        finally:
            source.close()

    if config.reader_mode == "hybrid":
        bot, user = build_source(config)
        try:
            bot_identity = bot.get_me()
            user_identity = user.client.get_me()
            return {
                "ok": True,
                "reader": "hybrid",
                "bot": bot_identity,
                "account": getattr(user_identity, "username", None)
                or getattr(user_identity, "first_name", None),
            }
        finally:
            bot.close()
            user.close()

    bot = bot_factory(config.token)
    identity = bot.get_me()
    return {"ok": True, "bot": identity}


def main() -> None:
    configure_logging()
    config = WorkerConfig.from_env()
    LOGGER.info(
        "Starting SuperDeal Telegram worker in %s reader mode for %d channel(s)",
        config.reader_mode,
        len(config.channels),
    )
    check_telegram(config)
    run_forever(config)


if __name__ == "__main__":
    main()
