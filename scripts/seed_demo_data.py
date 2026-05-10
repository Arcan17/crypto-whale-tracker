"""Seed configured database with deterministic demo whale transactions."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.database import SessionLocal, Transaction, init_db  # noqa: E402

SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_transactions.json"
SessionFactory = Callable[[], Any]


class DemoSeedError(ValueError):
    """Raised when demo seed data cannot be loaded or validated."""


def load_sample_transactions(
    sample_path: Path = SAMPLE_DATA_PATH,
) -> list[dict[str, Any]]:
    """Load demo whale transactions from a JSON file.

    Args:
        sample_path: Path to the sample transaction JSON file.

    Returns:
        A list of transaction dictionaries.

    Raises:
        DemoSeedError: If the JSON document is missing, invalid, or not a list.
    """
    try:
        with sample_path.open("r", encoding="utf-8") as sample_file:
            transactions = json.load(sample_file)
    except FileNotFoundError as exc:
        raise DemoSeedError(f"Demo data file not found: {sample_path}") from exc
    except json.JSONDecodeError as exc:
        raise DemoSeedError(f"Demo data file is not valid JSON: {sample_path}") from exc

    if not isinstance(transactions, list):
        raise DemoSeedError("Demo data must be a JSON list of transactions.")

    return transactions


def _created_at_from_payload(payload: dict[str, Any], now: datetime) -> datetime:
    """Build a timezone-aware created_at value from a demo payload."""
    if "created_at" in payload:
        value = str(payload["created_at"]).replace("Z", "+00:00")
        created_at = datetime.fromisoformat(value)
        if created_at.tzinfo is None:
            return created_at.replace(tzinfo=timezone.utc)
        return created_at.astimezone(timezone.utc)

    minutes_ago = int(payload.get("created_at_minutes_ago", 0))
    return now - timedelta(minutes=minutes_ago)


def _validate_payload(payload: dict[str, Any]) -> None:
    """Validate required fields for a demo transaction payload."""
    required_fields = {
        "tx_hash",
        "from_address",
        "from_label",
        "to_address",
        "to_label",
        "value_eth",
        "value_usd",
        "token_symbol",
        "block_number",
        "direction",
    }
    missing_fields = sorted(required_fields - payload.keys())
    if missing_fields:
        raise DemoSeedError(
            f"Demo transaction {payload.get('tx_hash', '<unknown>')} is missing: "
            f"{', '.join(missing_fields)}"
        )

    tx_hash = str(payload["tx_hash"])
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise DemoSeedError(f"Demo transaction has invalid tx_hash: {tx_hash}")

    for field_name in ("from_address", "to_address"):
        address = str(payload[field_name])
        if not address.startswith("0x") or len(address) != 42:
            raise DemoSeedError(
                f"Demo transaction {tx_hash} has invalid {field_name}: {address}"
            )


def _build_transaction(payload: dict[str, Any], now: datetime) -> Transaction:
    """Convert a demo payload into a Transaction ORM object."""
    _validate_payload(payload)
    return Transaction(
        tx_hash=str(payload["tx_hash"]),
        from_address=str(payload["from_address"]),
        from_label=str(payload["from_label"]),
        to_address=str(payload["to_address"]),
        to_label=str(payload["to_label"]),
        value_eth=float(payload["value_eth"]),
        value_usd=float(payload["value_usd"]),
        token_symbol=str(payload["token_symbol"]).upper(),
        block_number=int(payload["block_number"]),
        direction=str(payload["direction"]),
        created_at=_created_at_from_payload(payload, now),
    )


def seed_demo_data(
    session_factory: SessionFactory = SessionLocal,
    sample_path: Path = SAMPLE_DATA_PATH,
    ensure_schema: bool = True,
) -> tuple[int, int]:
    """Insert sample whale transactions into the configured database.

    Existing transactions are skipped by ``tx_hash`` so the seed can be run
    repeatedly without duplicating records.

    Args:
        session_factory: Callable returning a SQLAlchemy session.
        sample_path: JSON file containing demo transactions.
        ensure_schema: Whether to create configured database tables first.

    Returns:
        A tuple of ``(inserted_count, skipped_count)``.
    """
    if ensure_schema:
        init_db()

    payloads = load_sample_transactions(sample_path)
    now = datetime.now(timezone.utc)
    session = session_factory()
    inserted = 0
    skipped = 0

    try:
        for payload in payloads:
            if not isinstance(payload, dict):
                raise DemoSeedError("Each demo transaction must be a JSON object.")

            tx_hash = str(payload.get("tx_hash", ""))
            existing = session.query(Transaction).filter_by(tx_hash=tx_hash).first()
            if existing is not None:
                skipped += 1
                continue

            session.add(_build_transaction(payload, now))
            inserted += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted, skipped


def main() -> None:
    """Command-line entry point for seeding demo transactions."""
    inserted, skipped = seed_demo_data()
    print(
        "Demo seed complete: "
        f"inserted {inserted} transaction(s), skipped {skipped} existing transaction(s)."
    )


if __name__ == "__main__":
    main()
