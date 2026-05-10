"""Tests for wallet intelligence API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app, get_db
from models.database import Base, KnownWallet, Transaction

BINANCE = "0x28C6c06298d514Db089934071355E5743bf21d60"
UNKNOWN = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"
DB_KNOWN = "0x3333333333333333333333333333333333333333"


@pytest.fixture
def wallet_client():
    """Create a TestClient backed by a seeded in-memory SQLite database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    db.add(
        KnownWallet(
            address=DB_KNOWN,
            label="Research Fund",
            category="fund",
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
    )
    db.add_all(
        [
            Transaction(
                tx_hash="0x" + "a" * 64,
                from_address=OTHER,
                from_label="Unknown Wallet",
                to_address=UNKNOWN,
                to_label="Unknown Wallet",
                value_eth=100,
                value_usd=300000,
                token_symbol="ETH",
                block_number=100,
                direction="wallet_to_wallet",
                created_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            ),
            Transaction(
                tx_hash="0x" + "b" * 64,
                from_address=UNKNOWN,
                from_label="Unknown Wallet",
                to_address=BINANCE,
                to_label="Binance Hot Wallet",
                value_eth=200,
                value_usd=600000,
                token_symbol="ETH",
                block_number=101,
                direction="to_exchange",
                created_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
            ),
            Transaction(
                tx_hash="0x" + "c" * 64,
                from_address=UNKNOWN,
                from_label="Unknown Wallet",
                to_address=OTHER,
                to_label="Unknown Wallet",
                value_eth=750000,
                value_usd=750000,
                token_symbol="USDC",
                block_number=102,
                direction="wallet_to_wallet",
                created_at=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
            ),
            Transaction(
                tx_hash="0x" + "d" * 64,
                from_address=DB_KNOWN,
                from_label="Research Fund",
                to_address=OTHER,
                to_label="Unknown Wallet",
                value_eth=10,
                value_usd=35000,
                token_symbol="ETH",
                block_number=103,
                direction="wallet_to_wallet",
                created_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db.commit()
    db.close()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_wallet_summary_aggregates_seeded_transactions(wallet_client):
    """Wallet summary returns local aggregate intelligence for an address."""
    response = wallet_client.get(f"/wallet/{UNKNOWN}/summary")

    assert response.status_code == 200
    data = response.json()

    assert data["address"] == UNKNOWN
    assert data["label"] is None
    assert data["category"] is None
    assert data["total_incoming_usd"] == 300000
    assert data["total_outgoing_usd"] == 1350000
    assert data["largest_transaction_usd"] == 750000
    assert data["transaction_count"] == 3
    assert data["top_tokens"] == [
        {"symbol": "ETH", "count": 2, "volume_usd": 900000},
        {"symbol": "USDC", "count": 1, "volume_usd": 750000},
    ]
    assert data["first_seen"] == "2026-05-01T12:00:00"
    assert data["last_seen"] == "2026-05-03T12:00:00"


def test_wallet_summary_uses_static_labeler_for_known_address(wallet_client):
    """Wallet summary reuses the existing static address labeler."""
    response = wallet_client.get(f"/wallet/{BINANCE.lower()}/summary")

    assert response.status_code == 200
    data = response.json()

    assert data["label"] == "Binance Hot Wallet"
    assert data["category"] == "exchange"
    assert data["total_incoming_usd"] == 600000
    assert data["total_outgoing_usd"] == 0
    assert data["transaction_count"] == 1


def test_wallet_summary_uses_seeded_known_wallet_table(wallet_client):
    """Wallet summary checks locally seeded known_wallets before static labels."""
    response = wallet_client.get(f"/wallet/{DB_KNOWN}/summary")

    assert response.status_code == 200
    data = response.json()

    assert data["label"] == "Research Fund"
    assert data["category"] == "fund"
    assert data["total_outgoing_usd"] == 35000
    assert data["transaction_count"] == 1


def test_wallet_transactions_support_pagination_and_token_filter(wallet_client):
    """Wallet transactions returns matching rows with pagination and token filters."""
    response = wallet_client.get(f"/wallet/{UNKNOWN}/transactions?token=ETH&limit=1")

    assert response.status_code == 200
    data = response.json()

    assert data["address"] == UNKNOWN
    assert data["total"] == 2
    assert data["limit"] == 1
    assert len(data["transactions"]) == 1
    assert data["transactions"][0]["tx_hash"] == "0x" + "b" * 64
    assert data["transactions"][0]["token_symbol"] == "ETH"
