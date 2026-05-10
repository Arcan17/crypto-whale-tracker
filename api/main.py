"""FastAPI application exposing health, stats, and transaction query endpoints."""

from __future__ import annotations

import csv
import io
import logging
import time
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Generator, Optional
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, Query
from fastapi.responses import Response
from sqlalchemy.orm import Query as SQLAlchemyQuery
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

EXPORT_FIELDS = [
    "id",
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
    "created_at",
]

DOWNLOAD_HEADERS = {
    "Content-Disposition": "attachment",
    "X-Content-Type-Options": "nosniff",
}


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
# Helpers
# ---------------------------------------------------------------------------


def _apply_transaction_filters(
    query: SQLAlchemyQuery,
    *,
    token: Optional[str] = None,
    min_usd: Optional[float] = None,
) -> SQLAlchemyQuery:
    """Apply reusable transaction filters to a SQLAlchemy query."""
    if token:
        query = query.filter(Transaction.token_symbol.ilike(token))
    if min_usd is not None:
        query = query.filter(Transaction.value_usd >= min_usd)
    return query


def _serialize_transaction(tx: Transaction) -> dict[str, Any]:
    """Convert a transaction ORM object to API/export-friendly values."""
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


def _query_transaction_rows(
    db: Session,
    *,
    limit: int,
    token: Optional[str] = None,
    min_usd: Optional[float] = None,
) -> list[Transaction]:
    """Fetch transaction rows for downloadable exports."""
    query = _apply_transaction_filters(
        db.query(Transaction), token=token, min_usd=min_usd
    )
    return query.order_by(Transaction.created_at.desc()).limit(limit).all()


def _download_headers(filename: str) -> dict[str, str]:
    """Build safe response headers for a downloadable file."""
    headers = dict(DOWNLOAD_HEADERS)
    headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return headers


def _render_csv(rows: list[dict[str, Any]]) -> str:
    """Render serialized transaction rows as CSV text."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _excel_column_name(index: int) -> str:
    """Return the Excel column name for a 1-based column index."""
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_cell(row_index: int, column_index: int, value: Any) -> str:
    """Render a single XLSX worksheet cell using inline strings."""
    cell_ref = f"{_excel_column_name(column_index)}{row_index}"
    if value is None:
        value = ""
    if isinstance(value, Decimal):
        value = str(value)
    escaped_value = escape(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped_value}</t></is></c>'


def _render_worksheet(rows: list[dict[str, Any]]) -> str:
    """Render the XLSX worksheet XML for exported transactions."""
    worksheet_rows = []
    worksheet_rows.append(
        '<row r="1">'
        + "".join(
            _xlsx_cell(1, column_index, field)
            for column_index, field in enumerate(EXPORT_FIELDS, start=1)
        )
        + "</row>"
    )
    for row_index, row in enumerate(rows, start=2):
        worksheet_rows.append(
            f'<row r="{row_index}">'
            + "".join(
                _xlsx_cell(row_index, column_index, row.get(field))
                for column_index, field in enumerate(EXPORT_FIELDS, start=1)
            )
            + "</row>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>" + "".join(worksheet_rows) + "</sheetData></worksheet>"
    )


def _render_xlsx(rows: list[dict[str, Any]]) -> bytes:
    """Render serialized transaction rows as a minimal XLSX workbook."""
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Transactions" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": _render_worksheet(rows),
    }

    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return workbook.getvalue()


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
    min_usd: Optional[float] = Query(
        default=None, ge=0, description="Minimum USD value to include"
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Query stored whale transactions with optional filters and pagination.

    Args:
        limit: Maximum number of records to return (1–200, default 20).
        skip: Number of records to skip for pagination.
        token: Optional token symbol filter (case-insensitive).
        min_usd: Optional minimum USD value filter.
        db: Injected SQLAlchemy session.

    Returns:
        JSON object with ``total``, ``skip``, ``limit``, and ``transactions`` list.
    """
    query = _apply_transaction_filters(
        db.query(Transaction), token=token, min_usd=min_usd
    )

    total: int = query.count()
    rows = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()

    transactions = [_serialize_transaction(tx) for tx in rows]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "transactions": transactions,
    }


@app.get("/transactions/export.csv", summary="Export whale transactions as CSV")
async def export_transactions_csv(
    limit: int = Query(
        default=200, ge=1, le=1000, description="Maximum records to export"
    ),
    token: Optional[str] = Query(
        default=None, description="Filter by token symbol (e.g. USDC)"
    ),
    min_usd: Optional[float] = Query(
        default=None, ge=0, description="Minimum USD value to include"
    ),
    db: Session = Depends(get_db),
) -> Response:
    """Export whale transactions as a downloadable CSV file."""
    rows = [
        _serialize_transaction(tx)
        for tx in _query_transaction_rows(db, limit=limit, token=token, min_usd=min_usd)
    ]
    return Response(
        content=_render_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers=_download_headers("transactions.csv"),
    )


@app.get("/transactions/export.xlsx", summary="Export whale transactions as Excel")
async def export_transactions_xlsx(
    limit: int = Query(
        default=200, ge=1, le=1000, description="Maximum records to export"
    ),
    token: Optional[str] = Query(
        default=None, description="Filter by token symbol (e.g. USDC)"
    ),
    min_usd: Optional[float] = Query(
        default=None, ge=0, description="Minimum USD value to include"
    ),
    db: Session = Depends(get_db),
) -> Response:
    """Export whale transactions as a downloadable XLSX workbook."""
    rows = [
        _serialize_transaction(tx)
        for tx in _query_transaction_rows(db, limit=limit, token=token, min_usd=min_usd)
    ]
    return Response(
        content=_render_xlsx(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_download_headers("transactions.xlsx"),
    )
