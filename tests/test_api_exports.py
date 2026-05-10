"""Tests for transaction API export endpoints."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app, get_db
from models.database import Base, Transaction


@pytest.fixture
def api_client():
    """Create a TestClient backed by an isolated in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    now = datetime.now(timezone.utc)
    with testing_session() as db:
        db.add_all(
            [
                Transaction(
                    tx_hash="0x" + "a" * 64,
                    from_address="0x" + "1" * 40,
                    from_label="Binance Hot Wallet",
                    to_address="0x" + "2" * 40,
                    to_label="Unknown Wallet",
                    value_eth=10,
                    value_usd=30_000,
                    token_symbol="ETH",
                    block_number=100,
                    direction="from_exchange",
                    created_at=now - timedelta(minutes=2),
                ),
                Transaction(
                    tx_hash="0x" + "b" * 64,
                    from_address="0x" + "3" * 40,
                    from_label="Coinbase",
                    to_address="0x" + "4" * 40,
                    to_label="Unknown Wallet",
                    value_eth=1_000_000,
                    value_usd=1_000_000,
                    token_symbol="USDC",
                    block_number=101,
                    direction="from_exchange",
                    created_at=now,
                ),
            ]
        )
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_transactions_csv_export_supports_filters(api_client: TestClient) -> None:
    """CSV export returns filtered transaction rows with download headers."""
    response = api_client.get("/transactions/export.csv?token=USDC&min_usd=500000&limit=10")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == ('attachment; filename="transactions.csv"')
    assert response.headers["x-content-type-options"] == "nosniff"

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["token_symbol"] == "USDC"
    assert rows[0]["value_usd"] == "1000000.00"


def test_transactions_xlsx_export_supports_filters(api_client: TestClient) -> None:
    """XLSX export returns a valid workbook with filtered transaction rows."""
    response = api_client.get("/transactions/export.xlsx?token=ETH&min_usd=10000&limit=10")

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == ('attachment; filename="transactions.xlsx"')
    assert response.headers["x-content-type-options"] == "nosniff"

    with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml")

    root = ET.fromstring(sheet_xml)
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values = [text.text for text in root.findall(".//main:t", namespace) if text.text is not None]

    assert "token_symbol" in values
    assert "ETH" in values
    assert "USDC" not in values
    assert "30000.00" in values
