"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """All application configuration, sourced from environment variables.

    Attributes:
        ALCHEMY_WS_URL: WebSocket URL for Alchemy Ethereum node.
        TELEGRAM_BOT_TOKEN: Telegram bot API token.
        TELEGRAM_CHAT_ID: Telegram chat/channel ID to send alerts to.
        MIN_WHALE_USD: Minimum USD value to qualify a transaction as a whale alert.
        DATABASE_URL: SQLAlchemy-compatible database connection string.
        HEALTH_PORT: Port for the FastAPI health/stats server.
        LOG_LEVEL: Python logging level (DEBUG, INFO, WARNING, ERROR).
        MONITOR_TOKENS: List of token symbols to monitor.
    """

    ALCHEMY_WS_URL: str = "wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    MIN_WHALE_USD: float = 500_000.0
    DATABASE_URL: str = "sqlite:///./data/whales.db"
    HEALTH_PORT: int = 8080
    LOG_LEVEL: str = "INFO"
    MONITOR_TOKENS: List[str] = field(
        default_factory=lambda: ["ETH", "USDT", "USDC", "WETH"]
    )


def get_settings() -> Settings:
    """Create and return a Settings instance populated from environment variables.

    Returns:
        A fully configured Settings dataclass instance.
    """
    raw_tokens = os.getenv("MONITOR_TOKENS", "ETH,USDT,USDC,WETH")
    monitor_tokens = [t.strip() for t in raw_tokens.split(",") if t.strip()]

    return Settings(
        ALCHEMY_WS_URL=os.getenv(
            "ALCHEMY_WS_URL", "wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
        ),
        TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID", ""),
        MIN_WHALE_USD=float(os.getenv("MIN_WHALE_USD", "500000")),
        DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./data/whales.db"),
        HEALTH_PORT=int(os.getenv("HEALTH_PORT", "8080")),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        MONITOR_TOKENS=monitor_tokens,
    )
