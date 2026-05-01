"""Tests for analysis.filter.TransactionFilter."""

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysis.filter import TransactionFilter, WhaleTransaction
from tests.conftest import make_erc20_log, make_empty_receipt, make_eth_tx

# ---------------------------------------------------------------------------
# Helpers / known addresses
# ---------------------------------------------------------------------------

# USDC contract address (checksummed)
USDC_CONTRACT = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
# USDT contract address (checksummed)
USDT_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
# WETH contract address (checksummed)
WETH_CONTRACT = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

SENDER = "0x28C6c06298d514Db089934071355E5743bf21d60"
RECEIVER = "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3"

# $500k / $3000 per ETH ≈ 166.67 ETH → 166_670_000_000_000_000_000 wei (above)
WHALE_ETH_WEI = 167 * 10**18  # ~$501k at $3000/ETH
SMALL_ETH_WEI = 1 * 10**18  # $3 000 — below threshold


# ---------------------------------------------------------------------------
# 1. ETH transaction above threshold is detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eth_transaction_above_threshold_is_detected(settings, mock_eth_price):
    """A plain ETH transfer worth >= MIN_WHALE_USD must return a WhaleTransaction."""
    tx_filter = TransactionFilter(settings)
    tx = make_eth_tx(WHALE_ETH_WEI)
    receipt = make_empty_receipt()

    result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is not None
    assert isinstance(result, WhaleTransaction)
    assert result.token_symbol == "ETH"
    assert result.value_usd >= settings.MIN_WHALE_USD


# ---------------------------------------------------------------------------
# 2. ETH transaction below threshold is ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eth_transaction_below_threshold_is_ignored(settings, mock_eth_price):
    """A plain ETH transfer worth < MIN_WHALE_USD must return None."""
    tx_filter = TransactionFilter(settings)
    tx = make_eth_tx(SMALL_ETH_WEI)
    receipt = make_empty_receipt()

    result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is None


# ---------------------------------------------------------------------------
# 3. USDC transfer >= $500k is detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_transfer_usdc_detected(settings, mock_eth_price):
    """A USDC ERC-20 transfer worth >= MIN_WHALE_USD must be detected."""
    tx_filter = TransactionFilter(settings)

    # USDC has 6 decimals; $600_000 = 600_000 * 10^6 raw units
    amount_raw = 600_000 * 10**6
    log = make_erc20_log(USDC_CONTRACT, SENDER, RECEIVER, amount_raw)

    tx = make_eth_tx(0)  # no ETH value
    receipt = make_empty_receipt(logs=[log])

    result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is not None
    assert result.token_symbol == "USDC"
    assert result.value_usd >= settings.MIN_WHALE_USD


# ---------------------------------------------------------------------------
# 4. USDC transfer below threshold is ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_transfer_below_threshold_ignored(settings, mock_eth_price):
    """A USDC ERC-20 transfer worth < MIN_WHALE_USD must return None."""
    tx_filter = TransactionFilter(settings)

    # $100 in USDC
    amount_raw = 100 * 10**6
    log = make_erc20_log(USDC_CONTRACT, SENDER, RECEIVER, amount_raw)

    tx = make_eth_tx(0)
    receipt = make_empty_receipt(logs=[log])

    result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is None


# ---------------------------------------------------------------------------
# 5. USD conversion uses the current ETH price
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usd_conversion_uses_current_price(settings):
    """ETH → USD conversion must use the price returned by get_eth_price."""
    eth_price = 4000.0  # deliberately different from the default fixture

    with patch.object(
        TransactionFilter,
        "get_eth_price",
        new_callable=AsyncMock,
        return_value=eth_price,
    ):
        tx_filter = TransactionFilter(settings)
        # 200 ETH * $4000 = $800k > $500k threshold
        value_wei = 200 * 10**18
        tx = make_eth_tx(value_wei)
        receipt = make_empty_receipt()

        result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is not None
    expected_usd = 200 * eth_price
    assert abs(result.value_usd - expected_usd) < 1.0  # allow rounding


# ---------------------------------------------------------------------------
# 6. ETH price is cached (only one HTTP call for two uses within 60 s)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eth_price_is_cached(settings):
    """get_eth_price must only make one HTTP call within the 60-second TTL."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"ethereum": {"usd": 3500.0}}

    with patch("httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client_instance

        tx_filter = TransactionFilter(settings)

        price1 = await tx_filter.get_eth_price()
        price2 = await tx_filter.get_eth_price()

    assert price1 == 3500.0
    assert price2 == 3500.0
    # The underlying HTTP GET should have been called only once.
    assert mock_client_instance.get.call_count == 1


# ---------------------------------------------------------------------------
# 7. Transaction with no token logs and zero ETH value is ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_with_no_token_logs_and_zero_eth_ignored(
    settings, mock_eth_price
):
    """A transaction with zero ETH and no Transfer logs must return None."""
    tx_filter = TransactionFilter(settings)
    tx = make_eth_tx(0)
    receipt = make_empty_receipt(logs=[])

    result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is None


# ---------------------------------------------------------------------------
# 8. WETH transfer >= threshold is detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weth_transfer_detected(settings, mock_eth_price):
    """A WETH ERC-20 transfer worth >= MIN_WHALE_USD must be detected.

    mock_eth_price returns $3000; 200 WETH * $3000 = $600k > $500k.
    """
    tx_filter = TransactionFilter(settings)

    # WETH has 18 decimals; 200 WETH = 200 * 10^18 raw units
    amount_raw = 200 * 10**18
    log = make_erc20_log(WETH_CONTRACT, SENDER, RECEIVER, amount_raw)

    tx = make_eth_tx(0)
    receipt = make_empty_receipt(logs=[log])

    result = await tx_filter.analyze_transaction(tx, receipt)

    assert result is not None
    assert result.token_symbol == "WETH"
    assert result.value_usd >= settings.MIN_WHALE_USD
