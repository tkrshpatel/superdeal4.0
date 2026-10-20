"""LAN-ready API entry point for running SuperDeal on a personal PC."""

from __future__ import annotations

import logging
import os

from .api import serve
from .database import connect


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("SUPERDEAL_API_HOST", "127.0.0.1")
    port = int(os.getenv("SUPERDEAL_API_PORT", "8000"))
    database = os.getenv("SUPERDEAL_DB", "data/superdeal.db")
    connection = connect(database, check_same_thread=False)
    logging.getLogger("superdeal.api").info(
        "SuperDeal API listening on %s:%d using database %s", host, port, database
    )
    serve(connection, host=host, port=port)


if __name__ == "__main__":
    main()
