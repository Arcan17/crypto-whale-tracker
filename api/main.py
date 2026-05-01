"""FastAPI application exposing health, stats, and transaction query endpoints."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from fastapi import Depends, FastAPI, Query
from sqlalchemy.orm import Session

from models.database import SessionLocal, Transaction

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

    transactions = [
        {
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
        for tx in rows
    ]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "transactions": transactions,
    }
