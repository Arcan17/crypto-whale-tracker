"""SQLAlchemy database models and session management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Numeric,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from config.settings import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

engine = create_engine(
    _settings.DATABASE_URL,
    connect_args=({"check_same_thread": False} if "sqlite" in _settings.DATABASE_URL else {}),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""

    pass


class Transaction(Base):
    """ORM model representing a detected whale transaction.

    Attributes:
        id: Auto-incrementing primary key.
        tx_hash: Unique Ethereum transaction hash (0x-prefixed, 66 chars).
        from_address: Sender's Ethereum address.
        from_label: Human-readable label for the sender (e.g. "Binance Hot Wallet").
        to_address: Recipient's Ethereum address.
        to_label: Human-readable label for the recipient.
        value_eth: Transaction value in ETH (or token equivalent).
        value_usd: Transaction value in USD at time of detection.
        token_symbol: Token symbol (e.g. "ETH", "USDT").
        block_number: Ethereum block number containing the transaction.
        direction: Categorised direction (from_exchange / to_exchange / wallet_to_wallet).
        created_at: UTC timestamp when this record was inserted.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True, nullable=False)
    from_address: Mapped[str] = mapped_column(String(42), nullable=False)
    from_label: Mapped[str] = mapped_column(String(100), default="Unknown Wallet", nullable=False)
    to_address: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    to_label: Mapped[str] = mapped_column(String(100), default="Unknown Wallet", nullable=False)
    value_eth: Mapped[float] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    value_usd: Mapped[float] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    token_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    block_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    direction: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class KnownWallet(Base):
    """ORM model representing a known wallet address with its label and category.

    Attributes:
        id: Auto-incrementing primary key.
        address: Ethereum address (checksum format).
        label: Human-readable wallet label (e.g. "Coinbase").
        category: Wallet category (exchange, defi, bridge, stablecoin).
        created_at: UTC timestamp when this record was inserted.
    """

    __tablename__ = "known_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def init_db() -> None:
    """Create all database tables if they do not already exist.

    This function is idempotent — safe to call on every application start.
    """
    logger.info("Initialising database schema at %s", _settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    logger.info("Database schema ready.")
