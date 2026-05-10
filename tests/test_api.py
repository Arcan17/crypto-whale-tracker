"""Tests for the FastAPI health, stats, transaction, and export endpoints."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.main import app, get_db
from models.database import Base, Transaction


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    """Create a TestClient backed by an isolated temporary SQLite database."""
    database_url = f"sqlite:///{tmp_path / 'api_test.sqlite'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    seed_transactions = [
        Transaction(
            tx_hash="0x" + "a" * 64,
            from_address="0x28C6c06298d514Db089934071355E5743bf21d60",
            from_label="Binance Hot Wallet",
            to_address="0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",
            to_label="Coinbase",
            value_eth=250.0,
            value_usd=750_000.0,
            token_symbol="ETH",
            block_number=19_000_001,
            direction="from_exchange",
            created_at=now,
        ),
        Transaction(
            tx_hash="0x" + "b" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            from_label="Unknown Wallet",
            to_address="0x28C6c06298d514Db089934071355E5743bf21d60",
            to_label="Binance Hot Wallet",
            value_eth=1_200_000.0,
            value_usd=1_200_000.0,
            token_symbol="USDC",
            block_number=19_000_002,
            direction="to_exchange",
            created_at=now + timedelta(seconds=10),
        ),
        Transaction(
            tx_hash="0x" + "c" * 64,
            from_address="0x2222222222222222222222222222222222222222",
            from_label="Unknown Wallet",
            to_address="0x3333333333333333333333333333333333333333",
            to_label="Unknown Wallet",
            value_eth=900_000.0,
            value_usd=900_000.0,
            token_symbol="USDC",
            block_number=18_999_999,
            direction="wallet_to_wallet",
            created_at=yesterday,
        ),
    ]

    with testing_session_local() as db:
        db.add_all(seed_transactions)
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_health_endpoint(client: TestClient) -> None:
    """GET /health returns a healthy status without external service keys."""
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["connected"] is False
    assert isinstance(payload["uptime_seconds"], float)


def test_stats_endpoint(client: TestClient) -> None:
    """GET /stats aggregates only rows created during the current UTC day."""
    response = client.get("/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_alerts_today"] == 2
    assert payload["total_volume_usd_today"] == 1_950_000.0
    assert payload["top_tokens"] == [
        {"symbol": "ETH", "count": 1},
        {"symbol": "USDC", "count": 1},
    ]
    assert payload["last_alert_at"] is not None


def test_transactions_endpoint(client: TestClient) -> None:
    """GET /transactions returns seeded transactions in descending creation order."""
    response = client.get("/transactions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["skip"] == 0
    assert payload["limit"] == 20
    assert [tx["token_symbol"] for tx in payload["transactions"]] == [
        "USDC",
        "ETH",
        "USDC",
    ]
    assert payload["transactions"][0]["tx_hash"] == "0x" + "b" * 64


def test_transactions_endpoint_filters_by_token(client: TestClient) -> None:
    """GET /transactions?token=USDC returns only matching token rows."""
    response = client.get("/transactions", params={"token": "USDC"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["transactions"]) == 2
    assert {tx["token_symbol"] for tx in payload["transactions"]} == {"USDC"}


def test_transactions_export_csv_endpoint(client: TestClient) -> None:
    """GET /transactions/export.csv returns a CSV file with seeded rows."""
    response = client.get("/transactions/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "transactions.csv" in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 3
    assert rows[0]["tx_hash"] == "0x" + "b" * 64
    assert rows[0]["token_symbol"] == "USDC"
    assert rows[1]["token_symbol"] == "ETH"


def test_transactions_export_xlsx_endpoint(client: TestClient) -> None:
    """GET /transactions/export.xlsx returns a valid XLSX workbook."""
    response = client.get("/transactions/export.xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "transactions.xlsx" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode()

    assert "tx_hash" in sheet_xml
    assert "0x" + "b" * 64 in sheet_xml
    assert "USDC" in sheet_xml
