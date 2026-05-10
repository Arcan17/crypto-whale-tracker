"""Tests for demo data seeding."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, Transaction
from scripts.seed_demo_data import DemoSeedError, seed_demo_data


def _write_sample(path: Path) -> None:
    """Write a minimal valid demo transaction fixture."""
    path.write_text(
        json.dumps(
            [
                {
                    "tx_hash": "0xde000000000000000000000000000000000000000000000000000000000000aa",
                    "from_address": "0xA11cE000000000000000000000000000000000AA",
                    "from_label": "Demo Binance Hot Wallet",
                    "to_address": "0xD3a00000000000000000000000000000000000AA",
                    "to_label": "Demo Whale Cold Wallet",
                    "value_eth": 500.0,
                    "value_usd": 1750000.0,
                    "token_symbol": "eth",
                    "block_number": 19876543,
                    "direction": "from_exchange",
                    "created_at": "2026-05-10T12:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )


@pytest.fixture
def session_factory(tmp_path):
    """Return an isolated SQLite session factory for seed tests."""
    db_path = tmp_path / "demo.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_seed_demo_data_inserts_sample_transactions(session_factory, tmp_path):
    """Demo seed inserts validated whale transactions into the database."""
    sample_path = tmp_path / "sample_transactions.json"
    _write_sample(sample_path)

    inserted, skipped = seed_demo_data(
        session_factory=session_factory,
        sample_path=sample_path,
        ensure_schema=False,
    )

    assert inserted == 1
    assert skipped == 0

    session = session_factory()
    try:
        row = session.query(Transaction).one()
        assert row.tx_hash.endswith("aa")
        assert row.token_symbol == "ETH"
        assert float(row.value_usd) == 1_750_000.0
        assert row.created_at == datetime(2026, 5, 10, 12, 0)
    finally:
        session.close()


def test_seed_demo_data_is_idempotent(session_factory, tmp_path):
    """Running the demo seed repeatedly skips existing tx_hash values."""
    sample_path = tmp_path / "sample_transactions.json"
    _write_sample(sample_path)

    first_inserted, first_skipped = seed_demo_data(
        session_factory=session_factory,
        sample_path=sample_path,
        ensure_schema=False,
    )
    second_inserted, second_skipped = seed_demo_data(
        session_factory=session_factory,
        sample_path=sample_path,
        ensure_schema=False,
    )

    assert (first_inserted, first_skipped) == (1, 0)
    assert (second_inserted, second_skipped) == (0, 1)

    session = session_factory()
    try:
        assert session.query(Transaction).count() == 1
    finally:
        session.close()


def test_seed_demo_data_rejects_invalid_payload(session_factory, tmp_path):
    """Invalid demo records fail loudly instead of partially seeding bad data."""
    sample_path = tmp_path / "bad_sample_transactions.json"
    sample_path.write_text(
        json.dumps([{"tx_hash": "not-a-realistic-hash"}]), encoding="utf-8"
    )

    with pytest.raises(DemoSeedError):
        seed_demo_data(
            session_factory=session_factory,
            sample_path=sample_path,
            ensure_schema=False,
        )
