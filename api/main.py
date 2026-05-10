"""FastAPI application exposing health, stats, and transaction query endpoints."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from fastapi import Depends, FastAPI, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from analysis.labeler import get_category, get_label
from models.database import KnownWallet, SessionLocal, Transaction

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Crypto Whale Tracker",
    description="REST API for querying detected whale transactions.",
    version="1.0.0",
)

# Track application start time to calculate uptime.
_start_time: float = time.monotonic()

# Injected at runtime by main.py so the API can report connection status.
_feed_ref: Any = None


def set_feed(feed: Any) -> None:
    """Register the :class:`~feeds.ethereum_feed.EthereumFeed` instance for health reporting.

    Args:
        feed: The running EthereumFeed instance.
    """
    global _feed_ref
    _feed_ref = feed


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session per request.

    Yields:
        An active SQLAlchemy :class:`~sqlalchemy.orm.Session`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Wallet intelligence helpers
# ---------------------------------------------------------------------------

UNKNOWN_WALLET_LABEL = "Unknown Wallet"


def _normalise_address(address: str) -> str:
    """Return a lowercase address for case-insensitive database lookups."""
    return address.lower()


def _transaction_matches_wallet_query(address: str):
    """Build a SQLAlchemy filter matching transactions involving an address."""
    normalized_address = _normalise_address(address)
    return or_(
        func.lower(Transaction.from_address) == normalized_address,
        func.lower(Transaction.to_address) == normalized_address,
    )


def _wallet_label_from_db(
    db: Session, address: str
) -> tuple[Optional[str], Optional[str]]:
    """Return a wallet label/category from the local database if available."""
    wallet = (
        db.query(KnownWallet)
        .filter(func.lower(KnownWallet.address) == _normalise_address(address))
        .first()
    )
    if wallet is None:
        return None, None
    return wallet.label, wallet.category


def _wallet_label(address: str, db: Session) -> tuple[Optional[str], Optional[str]]:
    """Resolve wallet intelligence from local sources without external calls.

    Database-backed known wallets are checked first so operators can seed or
    override labels. The static labeler registry is used as a fallback.
    """
    db_label, db_category = _wallet_label_from_db(db, address)
    if db_label is not None:
        return db_label, db_category

    label = get_label(address)
    if label == UNKNOWN_WALLET_LABEL:
        return None, None

    category = get_category(label)
    return label, None if category == "unknown" else category


def _transaction_to_dict(tx: Transaction) -> dict[str, Any]:
    """Serialise a transaction ORM row for API responses."""
    return {
        "id": tx.id,
        "tx_hash": tx.tx_hash,
        "from_address": tx.from_address,
        "from_label": tx.from_label,
        "to_address": tx.to_address,
        "to_label": tx.to_label,
        "value_eth": str(tx.value_eth),
        "value_usd": str(tx.value_usd),
        "token_symbol": tx.token_symbol,
        "block_number": tx.block_number,
        "direction": tx.direction,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", summary="Health check")
async def health() -> dict[str, Any]:
    """Return application health status and uptime.

    Returns:
        JSON object with ``status``, ``connected`` (feed WebSocket state),
        and ``uptime_seconds``.
    """
    connected = bool(_feed_ref and getattr(_feed_ref, "connected", False))
    uptime = time.monotonic() - _start_time
    return {
        "status": "healthy",
        "connected": connected,
        "uptime_seconds": round(uptime, 2),
    }


@app.get("/stats", summary="Aggregated statistics")
async def stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return aggregated statistics for today's whale alerts.

    Returns:
        JSON object with ``total_alerts_today``, ``total_volume_usd_today``,
        ``top_tokens`` (top 5 by count), and ``last_alert_at``.
    """
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    today_txs = (
        db.query(Transaction).filter(Transaction.created_at >= today_start).all()
    )

    total_alerts = len(today_txs)
    total_volume = sum(float(tx.value_usd) for tx in today_txs)

    # Count per token symbol.
    token_counts: dict[str, int] = {}
    for tx in today_txs:
        token_counts[tx.token_symbol] = token_counts.get(tx.token_symbol, 0) + 1

    top_tokens = sorted(
        [{"symbol": sym, "count": cnt} for sym, cnt in token_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:5]

    last_tx = db.query(Transaction).order_by(Transaction.created_at.desc()).first()
    last_alert_at: Optional[str] = (
        last_tx.created_at.isoformat() if last_tx is not None else None
    )

    return {
        "total_alerts_today": total_alerts,
        "total_volume_usd_today": round(total_volume, 2),
        "top_tokens": top_tokens,
        "last_alert_at": last_alert_at,
    }


@app.get("/transactions", summary="List whale transactions")
async def list_transactions(
    limit: int = Query(
        default=20, ge=1, le=200, description="Maximum records to return"
    ),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    token: Optional[str] = Query(
        default=None, description="Filter by token symbol (e.g. USDC)"
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Query stored whale transactions with optional token filter and pagination.

    Args:
        limit: Maximum number of records to return (1–200, default 20).
        skip: Number of records to skip for pagination.
        token: Optional token symbol filter (case-insensitive).
        db: Injected SQLAlchemy session.

    Returns:
        JSON object with ``total``, ``skip``, ``limit``, and ``transactions`` list.
    """
    query = db.query(Transaction)
    if token:
        query = query.filter(Transaction.token_symbol.ilike(token))

    total: int = query.count()
    rows = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()

    transactions = [_transaction_to_dict(tx) for tx in rows]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "transactions": transactions,
    }


@app.get("/wallet/{address}/summary", summary="Wallet intelligence summary")
async def wallet_summary(address: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return aggregate wallet intelligence for a locally stored address.

    The summary is computed only from persisted whale transactions and locally
    known wallet labels; this endpoint does not perform external API calls.
    """
    normalized_address = _normalise_address(address)
    label, category = _wallet_label(address, db)

    rows = (
        db.query(Transaction)
        .filter(_transaction_matches_wallet_query(address))
        .order_by(Transaction.created_at.asc())
        .all()
    )

    total_incoming_usd = 0.0
    total_outgoing_usd = 0.0
    largest_transaction_usd = 0.0
    token_totals: dict[str, dict[str, float | int | str]] = {}

    for tx in rows:
        value_usd = float(tx.value_usd)
        largest_transaction_usd = max(largest_transaction_usd, value_usd)

        token = tx.token_symbol
        if token not in token_totals:
            token_totals[token] = {"symbol": token, "count": 0, "volume_usd": 0.0}
        token_totals[token]["count"] = int(token_totals[token]["count"]) + 1
        token_totals[token]["volume_usd"] = (
            float(token_totals[token]["volume_usd"]) + value_usd
        )

        if tx.to_address and tx.to_address.lower() == normalized_address:
            total_incoming_usd += value_usd
        if tx.from_address.lower() == normalized_address:
            total_outgoing_usd += value_usd

    top_tokens = sorted(
        [
            {
                "symbol": str(token["symbol"]),
                "count": int(token["count"]),
                "volume_usd": round(float(token["volume_usd"]), 2),
            }
            for token in token_totals.values()
        ],
        key=lambda token: (token["volume_usd"], token["count"], token["symbol"]),
        reverse=True,
    )[:5]

    return {
        "address": address,
        "label": label,
        "category": category,
        "total_incoming_usd": round(total_incoming_usd, 2),
        "total_outgoing_usd": round(total_outgoing_usd, 2),
        "largest_transaction_usd": round(largest_transaction_usd, 2),
        "transaction_count": len(rows),
        "top_tokens": top_tokens,
        "first_seen": rows[0].created_at.isoformat() if rows else None,
        "last_seen": rows[-1].created_at.isoformat() if rows else None,
    }


@app.get("/wallet/{address}/transactions", summary="List wallet transactions")
async def wallet_transactions(
    address: str,
    limit: int = Query(
        default=20, ge=1, le=200, description="Maximum records to return"
    ),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    token: Optional[str] = Query(
        default=None, description="Filter by token symbol (e.g. USDC)"
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List locally stored whale transactions involving a wallet address."""
    query = db.query(Transaction).filter(_transaction_matches_wallet_query(address))
    if token:
        query = query.filter(Transaction.token_symbol.ilike(token))

    total = query.count()
    rows = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "address": address,
        "total": total,
        "skip": skip,
        "limit": limit,
        "transactions": [_transaction_to_dict(tx) for tx in rows],
    }
