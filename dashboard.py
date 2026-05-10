"""Streamlit analytics dashboard for stored whale transactions.

The dashboard reads from the existing SQLAlchemy database layer used by the
FastAPI app. It does not start the Ethereum feed or require live Alchemy
credentials, so it can be opened against any database that already contains
transaction rows.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import select

from models.database import KnownWallet, SessionLocal, Transaction, init_db


UNKNOWN_LABEL = "Unknown Wallet"


@st.cache_data(ttl=30)
def load_transactions() -> pd.DataFrame:
    """Load all stored whale transactions into a pandas DataFrame."""
    init_db()
    with SessionLocal() as db:
        wallet_rows = db.execute(select(KnownWallet)).scalars()
        wallet_categories = {
            wallet.address.lower(): wallet.category for wallet in wallet_rows
        }
        rows = db.execute(
            select(Transaction).order_by(Transaction.created_at.desc())
        ).scalars()
        records = [transaction_to_record(tx, wallet_categories) for tx in rows]

    return pd.DataFrame.from_records(records)


def transaction_to_record(
    tx: Transaction, wallet_categories: dict[str, str]
) -> dict[str, Any]:
    """Convert a Transaction ORM object into dashboard-friendly primitives."""
    from_category = wallet_categories.get(tx.from_address.lower())
    to_category = (
        wallet_categories.get(tx.to_address.lower()) if tx.to_address else None
    )

    return {
        "id": tx.id,
        "tx_hash": tx.tx_hash,
        "from_address": tx.from_address,
        "from_label": tx.from_label,
        "to_address": tx.to_address,
        "to_label": tx.to_label,
        "value_eth": numeric_to_float(tx.value_eth),
        "value_usd": numeric_to_float(tx.value_usd),
        "token_symbol": tx.token_symbol,
        "block_number": tx.block_number,
        "direction": tx.direction,
        "from_category": from_category,
        "to_category": to_category,
        "created_at": tx.created_at,
    }


def numeric_to_float(value: Any) -> float:
    """Return SQLAlchemy numeric values as floats for Streamlit metrics/charts."""
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def apply_filters(
    transactions: pd.DataFrame,
    token: str,
    minimum_usd: float,
    direction: str,
) -> pd.DataFrame:
    """Apply dashboard filters to the transaction DataFrame."""
    filtered = transactions.copy()

    if token != "All":
        filtered = filtered[filtered["token_symbol"] == token]

    filtered = filtered[filtered["value_usd"] >= minimum_usd]

    if direction != "All":
        filtered = filtered[
            (filtered["direction"] == direction)
            | (filtered["from_category"] == direction)
            | (filtered["to_category"] == direction)
        ]

    return filtered


def render_metric_cards(transactions: pd.DataFrame) -> None:
    """Render headline transaction count and USD volume metrics."""
    total_transactions = len(transactions)
    total_volume = transactions["value_usd"].sum() if not transactions.empty else 0

    count_col, volume_col = st.columns(2)
    count_col.metric("Total whale transactions", f"{total_transactions:,}")
    volume_col.metric("Total USD volume", f"${total_volume:,.2f}")


def render_latest_transactions(transactions: pd.DataFrame) -> None:
    """Render the latest filtered whale transactions table."""
    st.subheader("Latest transactions")

    latest_columns = [
        "created_at",
        "token_symbol",
        "value_usd",
        "value_eth",
        "direction",
        "from_label",
        "to_label",
        "tx_hash",
    ]
    latest = transactions.head(50).loc[:, latest_columns]
    st.dataframe(latest, use_container_width=True, hide_index=True)


def render_top_tokens(transactions: pd.DataFrame) -> None:
    """Render top tokens by transaction count."""
    st.subheader("Top tokens")
    top_tokens = (
        transactions.groupby("token_symbol", dropna=False)
        .size()
        .reset_index(name="transactions")
        .sort_values("transactions", ascending=False)
    )
    st.dataframe(top_tokens.head(10), use_container_width=True, hide_index=True)


def render_top_labeled_entities(transactions: pd.DataFrame) -> None:
    """Render top non-unknown labels seen on either side of transactions."""
    st.subheader("Top labeled entities")
    labels = pd.concat(
        [
            transactions[["from_label", "value_usd"]].rename(
                columns={"from_label": "label"}
            ),
            transactions[["to_label", "value_usd"]].rename(
                columns={"to_label": "label"}
            ),
        ],
        ignore_index=True,
    )
    labels = labels[
        labels["label"].notna()
        & (labels["label"].str.strip() != "")
        & (labels["label"] != UNKNOWN_LABEL)
    ]

    if labels.empty:
        st.info("No labeled entities found in the filtered transactions.")
        return

    top_entities = (
        labels.groupby("label", dropna=False)
        .agg(transactions=("label", "size"), volume_usd=("value_usd", "sum"))
        .reset_index()
        .sort_values(["transactions", "volume_usd"], ascending=False)
    )
    st.dataframe(top_entities.head(10), use_container_width=True, hide_index=True)


def render_volume_by_token(transactions: pd.DataFrame) -> None:
    """Render volume by token as a table and bar chart."""
    st.subheader("Volume by token")
    volume_by_token = (
        transactions.groupby("token_symbol", dropna=False)["value_usd"]
        .sum()
        .reset_index(name="volume_usd")
        .sort_values("volume_usd", ascending=False)
    )
    st.bar_chart(volume_by_token, x="token_symbol", y="volume_usd")
    st.dataframe(volume_by_token, use_container_width=True, hide_index=True)


def render_filters(transactions: pd.DataFrame) -> tuple[str, float, str]:
    """Render sidebar controls and return selected filter values."""
    st.sidebar.header("Filters")

    tokens = ["All"] + sorted(transactions["token_symbol"].dropna().unique().tolist())
    token = st.sidebar.selectbox("Token", tokens)

    max_value = float(transactions["value_usd"].max() or 0)
    default_min = 0.0
    minimum_usd = st.sidebar.number_input(
        "Minimum USD value",
        min_value=0.0,
        max_value=max(max_value, default_min),
        value=default_min,
        step=10_000.0,
        format="%.2f",
    )

    directions = set(transactions["direction"].dropna().unique().tolist())
    directions.update(transactions["from_category"].dropna().unique().tolist())
    directions.update(transactions["to_category"].dropna().unique().tolist())
    direction = st.sidebar.selectbox("Direction/category", ["All"] + sorted(directions))

    return token, minimum_usd, direction


def render_download(transactions: pd.DataFrame) -> None:
    """Render a CSV download button for the filtered dataset."""
    csv = transactions.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered transactions as CSV",
        csv,
        file_name="whale_transactions.csv",
        mime="text/csv",
    )


def main() -> None:
    """Run the Streamlit dashboard."""
    st.set_page_config(page_title="Crypto Whale Tracker Dashboard", layout="wide")
    st.title("🐋 Crypto Whale Tracker Analytics")
    st.caption("Analytics for whale transactions stored in the configured database.")

    transactions = load_transactions()
    if transactions.empty:
        st.info(
            "No whale transactions found yet. Start the tracker to collect data, "
            "or point DATABASE_URL at an existing database."
        )
        return

    token, minimum_usd, direction = render_filters(transactions)
    filtered_transactions = apply_filters(
        transactions=transactions,
        token=token,
        minimum_usd=minimum_usd,
        direction=direction,
    )

    render_metric_cards(filtered_transactions)
    render_download(filtered_transactions)

    if filtered_transactions.empty:
        st.warning("No transactions match the current filters.")
        return

    table_col, token_col = st.columns([2, 1])
    with table_col:
        render_latest_transactions(filtered_transactions)
    with token_col:
        render_top_tokens(filtered_transactions)

    entity_col, volume_col = st.columns(2)
    with entity_col:
        render_top_labeled_entities(filtered_transactions)
    with volume_col:
        render_volume_by_token(filtered_transactions)


if __name__ == "__main__":
    main()
