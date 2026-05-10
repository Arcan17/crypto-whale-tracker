"""Entry point for the Crypto Whale Tracker application.

Starts three concurrent tasks:
- FastAPI HTTP server (health / stats / transactions)
- Ethereum WebSocket feed
All tasks share the same async event loop.
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from alerts.telegram_alert import TelegramAlert
from analysis.filter import TransactionFilter
from api.main import app as fastapi_app
from api.main import set_feed
from config.settings import Settings, get_settings
from feeds.ethereum_feed import EthereumFeed
from models.database import SessionLocal, init_db

logger = logging.getLogger(__name__)


async def main() -> None:
    """Configure and start all application components concurrently."""
    settings: Settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Initialising database…")
    init_db()

    feed = None
    if settings.DEMO_MODE:
        logger.info(
            "DEMO_MODE=true: skipping live Ethereum WebSocket and Telegram alert setup."
        )
        set_feed(None)
    else:
        alert = TelegramAlert(settings)
        tx_filter = TransactionFilter(settings)
        feed = EthereumFeed(settings, tx_filter, alert, SessionLocal)

        # Register feed with the API so /health can report connection status.
        set_feed(feed)

    # Configure uvicorn without using its built-in signal handlers so that
    # asyncio.gather() controls the lifecycle cleanly.
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=settings.HEALTH_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    logger.info("Starting Crypto Whale Tracker — API on port %d", settings.HEALTH_PORT)

    if settings.DEMO_MODE:
        await server.serve()
    else:
        await asyncio.gather(
            server.serve(),
            feed.start(),
        )


if __name__ == "__main__":
    asyncio.run(main())
