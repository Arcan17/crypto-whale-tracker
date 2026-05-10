"""Seed deterministic demo whale transactions for local portfolio walkthroughs."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.database import SessionLocal, Transaction, init_db  # noqa: E402

DEMO_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "tx_hash": "0x" + "a1" * 32,
        "from_address": "0x28C6c06298d514Db089934071355E5743bf21d60",
        "from_label": "Binance Hot Wallet",
        "to_address": "0x1111111111111111111111111111111111111111",
        "to_label": "Unknown Wallet",
        "value_eth": 410.0,
        "value_usd": 1_230_000.00,
        "token_symbol": "ETH",
        "block_number": 19_450_123,
        "direction": "from_exchange",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=18),
    },
    {
        "tx_hash": "0x" + "b2" * 32,
        "from_address": "0x2222222222222222222222222222222222222222",
        "from_label": "Unknown Wallet",
        "to_address": "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",
        "to_label": "Coinbase",
        "value_eth": 0.0,
        "value_usd": 875_000.00,
        "token_symbol": "USDC",
        "block_number": 19_450_456,
        "direction": "to_exchange",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=9),
    },
    {
        "tx_hash": "0x" + "c3" * 32,
        "from_address": "0x3333333333333333333333333333333333333333",
        "from_label": "Unknown Wallet",
        "to_address": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        "to_label": "Uniswap V2 Router",
        "value_eth": 225.0,
        "value_usd": 675_000.00,
        "token_symbol": "WETH",
        "block_number": 19_450_789,
        "direction": "wallet_to_wallet",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=3),
    },
]


def seed_demo_transactions() -> int:
    """Create demo transactions if they are not already present."""
    init_db()
    inserted = 0

    with SessionLocal() as db:
        for payload in DEMO_TRANSACTIONS:
            exists = (
                db.query(Transaction)
                .filter(Transaction.tx_hash == payload["tx_hash"])
                .first()
            )
            if exists is not None:
                continue

            db.add(Transaction(**payload))
            inserted += 1

        db.commit()

    return inserted


if __name__ == "__main__":
    created = seed_demo_transactions()
    print(f"Demo seed complete: {created} new transaction(s) inserted.")
