"""Shared pytest fixtures for the crypto-whale-tracker test suite."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from analysis.filter import TransactionFilter
from config.settings import Settings


# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Return a Settings instance pre-configured for testing.

    Returns:
        A :class:`~config.settings.Settings` with safe test defaults.
    """
    return Settings(
        ALCHEMY_WS_URL="wss://eth-mainnet.g.alchemy.com/v2/TEST_KEY",
        TELEGRAM_BOT_TOKEN="",
        TELEGRAM_CHAT_ID="",
        MIN_WHALE_USD=500_000.0,
        DATABASE_URL="sqlite:///:memory:",
        HEALTH_PORT=8081,
        LOG_LEVEL="DEBUG",
        MONITOR_TOKENS=["ETH", "USDT", "USDC", "WETH"],
    )


# ---------------------------------------------------------------------------
# ETH price mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_eth_price(settings: Settings):
    """Patch TransactionFilter.get_eth_price to return a fixed price of $3000.

    Yields:
        The patched :class:`~unittest.mock.AsyncMock` instance.
    """
    with patch.object(
        TransactionFilter, "get_eth_price", new_callable=AsyncMock, return_value=3000.0
    ) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Sample transaction dicts
# ---------------------------------------------------------------------------


def make_eth_tx(
    value_wei: int, tx_hash: str = "0xabc123", block: int = 19_000_000
) -> dict:
    """Create a minimal ETH transaction dict.

    Args:
        value_wei: Transaction value in wei.
        tx_hash: Transaction hash string.
        block: Block number.

    Returns:
        A dict matching the structure returned by web3.py.
    """
    return {
        "hash": tx_hash,
        "from": "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance Hot Wallet
        "to": "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",  # Coinbase
        "value": value_wei,
        "blockNumber": block,
        "gas": 21000,
        "gasPrice": 30_000_000_000,
        "nonce": 1,
    }


def make_empty_receipt(gas_used: int = 21000, logs: Optional[list] = None) -> dict:
    """Create a minimal transaction receipt dict with optional logs.

    Args:
        gas_used: Gas consumed.
        logs: List of log dicts; defaults to an empty list.

    Returns:
        A receipt dict.
    """
    return {
        "gasUsed": gas_used,
        "blockNumber": 19_000_000,
        "logs": logs or [],
        "status": 1,
    }


def make_erc20_log(
    contract_address: str,
    from_address: str,
    to_address: str,
    amount_int: int,
    topic0: Optional[str] = None,
) -> dict:
    """Build a synthetic ERC-20 Transfer event log dict.

    Args:
        contract_address: The token contract address.
        from_address: Sender address (will be zero-padded to 32 bytes in topics).
        to_address: Recipient address.
        amount_int: Raw integer transfer value (pre-decimals).
        topic0: Override for the Transfer event signature topic.

    Returns:
        A log dict in the format returned by web3.py.
    """
    from web3 import Web3
    from analysis.filter import TRANSFER_TOPIC

    def _pad(addr: str) -> str:
        """Zero-pad an address to a 32-byte hex string."""
        clean = addr.lower().removeprefix("0x")
        return "0x" + clean.zfill(64)

    data_hex = "0x" + hex(amount_int)[2:].zfill(64)

    return {
        "address": contract_address,
        "topics": [
            topic0 or TRANSFER_TOPIC,
            _pad(from_address),
            _pad(to_address),
        ],
        "data": data_hex,
    }
