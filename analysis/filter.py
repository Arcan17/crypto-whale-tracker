"""Transaction filtering logic — detects whale-sized transfers on Ethereum."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from web3 import Web3

from analysis.labeler import get_direction, get_label

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps ERC-20 contract address → (symbol, decimals)
KNOWN_TOKENS: dict[str, tuple[str, int]] = {
    "0xdAC17F958D2ee523a2206206994597C13D831ec7": ("USDT", 6),
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": ("USDC", 6),
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": ("WETH", 18),
}

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC: str = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# CoinGecko price endpoint
_COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"

# ETH has 18 decimals
_ETH_DECIMALS = Decimal(10**18)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class WhaleTransaction:
    """Represents a single whale-sized Ethereum transaction.

    Attributes:
        hash: Transaction hash (0x-prefixed).
        from_address: Sender address.
        to_address: Recipient address.
        value_eth: Transaction value expressed in ETH (or token units).
        value_usd: USD equivalent at time of detection.
        token_symbol: Token symbol (e.g. "ETH", "USDT", "WETH").
        block_number: Block number containing this transaction.
        timestamp: UTC datetime when the transaction was analysed.
        from_label: Human-readable label for the sender.
        to_label: Human-readable label for the recipient.
        direction: Categorised flow direction.
        gas_used: Gas consumed by the transaction.
    """

    hash: str
    from_address: str
    to_address: str
    value_eth: Decimal
    value_usd: float
    token_symbol: str
    block_number: int
    timestamp: datetime
    from_label: str
    to_label: str
    direction: str
    gas_used: int = 0


# ---------------------------------------------------------------------------
# TransactionFilter
# ---------------------------------------------------------------------------


class TransactionFilter:
    """Analyses raw Ethereum transactions and receipts to detect whale activity.

    A transaction qualifies as a whale event when its USD value is at or above
    ``settings.MIN_WHALE_USD``.  Both plain ETH transfers and ERC-20 Transfer
    events (USDT, USDC, WETH) are supported.
    """

    def __init__(self, settings: object) -> None:
        """Initialise the filter with application settings.

        Args:
            settings: A :class:`~config.settings.Settings` instance.
        """
        self._settings = settings
        self._eth_price_cache: Optional[float] = None
        self._eth_price_ts: float = 0.0
        self._price_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Price fetching
    # ------------------------------------------------------------------

    async def get_eth_price(self) -> float:
        """Fetch the current ETH/USD price from CoinGecko with a 60-second cache.

        Uses a lock to prevent multiple concurrent HTTP requests when the cache
        expires at the same time (thundering herd protection).

        Returns:
            Current ETH price in USD.
        """
        now = time.monotonic()
        if self._eth_price_cache is not None and (now - self._eth_price_ts) < 60:
            return self._eth_price_cache

        async with self._price_lock:
            # Re-check after acquiring lock — another coroutine may have updated.
            now = time.monotonic()
            if self._eth_price_cache is not None and (now - self._eth_price_ts) < 60:
                return self._eth_price_cache

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(_COINGECKO_URL)
                    response.raise_for_status()
                    data = response.json()
                    price: float = float(data["ethereum"]["usd"])
                    self._eth_price_cache = price
                    self._eth_price_ts = now
                    logger.debug("ETH price fetched: $%.2f", price)
                    return price
            except Exception as exc:
                logger.error("Failed to fetch ETH price: %s", exc)
                return self._eth_price_cache if self._eth_price_cache is not None else 0.0

    # ------------------------------------------------------------------
    # Public analysis entry point
    # ------------------------------------------------------------------

    async def analyze_transaction(self, tx: dict, receipt: dict) -> Optional[WhaleTransaction]:
        """Analyse a transaction and its receipt for whale-level activity.

        Checks native ETH value first, then inspects ERC-20 Transfer logs.  The
        first qualifying transfer found is returned.

        Args:
            tx: Transaction dict as returned by ``web3.eth.get_transaction``.
            receipt: Receipt dict as returned by ``web3.eth.get_transaction_receipt``.

        Returns:
            A :class:`WhaleTransaction` if the transaction qualifies, else ``None``.
        """
        if tx is None or receipt is None:
            return None

        eth_price = await self.get_eth_price()
        tx_hash: str = (
            tx.get("hash", b"").hex() if isinstance(tx.get("hash"), bytes) else tx.get("hash", "")
        )
        gas_used: int = receipt.get("gasUsed", 0)
        block_number: int = tx.get("blockNumber") or receipt.get("blockNumber", 0) or 0

        # ---- 1. Check native ETH value ----
        value_wei: int = int(tx.get("value", 0))
        if self._eth_value_above_threshold(value_wei, eth_price):
            value_eth = Decimal(value_wei) / _ETH_DECIMALS
            value_usd = float(value_eth) * eth_price
            from_addr: str = tx.get("from", "") or ""
            to_addr: str = tx.get("to", "") or ""
            from_label = get_label(from_addr)
            to_label = get_label(to_addr)
            direction = get_direction(from_label, to_label)
            return WhaleTransaction(
                hash=tx_hash,
                from_address=from_addr,
                to_address=to_addr,
                value_eth=value_eth,
                value_usd=value_usd,
                token_symbol="ETH",
                block_number=block_number,
                timestamp=datetime.now(timezone.utc),
                from_label=from_label,
                to_label=to_label,
                direction=direction,
                gas_used=gas_used,
            )

        # ---- 2. Check ERC-20 Transfer logs ----
        logs = receipt.get("logs", [])
        for log in logs:
            parsed = self._parse_token_transfer(log)
            if parsed is None:
                continue
            from_addr, to_addr, symbol, amount = parsed
            if self._token_value_above_threshold(amount, symbol, eth_price):
                # Convert token units to a USD value.
                if symbol in ("USDT", "USDC"):
                    value_usd = float(amount)
                elif symbol == "WETH":
                    value_usd = float(amount) * eth_price
                else:
                    value_usd = 0.0

                from_label = get_label(from_addr)
                to_label = get_label(to_addr)
                direction = get_direction(from_label, to_label)
                return WhaleTransaction(
                    hash=tx_hash,
                    from_address=from_addr,
                    to_address=to_addr,
                    value_eth=amount,
                    value_usd=value_usd,
                    token_symbol=symbol,
                    block_number=block_number,
                    timestamp=datetime.now(timezone.utc),
                    from_label=from_label,
                    to_label=to_label,
                    direction=direction,
                    gas_used=gas_used,
                )

        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_token_transfer(self, log: dict) -> Optional[tuple[str, str, str, Decimal]]:
        """Parse an ERC-20 Transfer event log.

        The Transfer event ABI is:
        ``Transfer(address indexed from, address indexed to, uint256 value)``

        Topics layout:
        * ``topics[0]`` — event signature hash
        * ``topics[1]`` — from address (zero-padded to 32 bytes)
        * ``topics[2]`` — to address (zero-padded to 32 bytes)
        * ``data``      — uint256 transfer value

        Args:
            log: A single log dict from a transaction receipt.

        Returns:
            A tuple ``(from_address, to_address, symbol, amount_in_token_units)``
            or ``None`` if the log is not a recognised Transfer event.
        """
        try:
            topics = log.get("topics", [])
            if len(topics) < 3:
                return None

            # Normalise topic[0] to a hex string for comparison.
            topic0 = topics[0]
            if isinstance(topic0, bytes):
                topic0 = "0x" + topic0.hex()
            if topic0.lower() != TRANSFER_TOPIC.lower():
                return None

            # Identify the ERC-20 contract by its address.
            contract_addr = log.get("address", "")
            try:
                contract_checksum = Web3.to_checksum_address(contract_addr)
            except Exception:
                return None

            token_info = KNOWN_TOKENS.get(contract_checksum)
            if token_info is None:
                return None
            symbol, decimals = token_info

            # Decode from/to from padded topics.
            def _topic_to_address(topic: object) -> str:
                if isinstance(topic, bytes):
                    raw = topic.hex()
                else:
                    raw = str(topic)
                # Strip leading zeros leaving the 40-char address.
                raw = raw.removeprefix("0x").removeprefix("0X")
                return Web3.to_checksum_address("0x" + raw[-40:])

            from_addr = _topic_to_address(topics[1])
            to_addr = _topic_to_address(topics[2])

            # Decode the uint256 value from log data.
            data = log.get("data", "0x")
            if isinstance(data, bytes):
                value_int = int.from_bytes(data, "big")
            else:
                data_hex = str(data).removeprefix("0x").removeprefix("0X") or "0"
                value_int = int(data_hex, 16)

            amount = Decimal(value_int) / Decimal(10**decimals)
            return from_addr, to_addr, symbol, amount

        except Exception as exc:
            logger.debug("Error parsing token transfer log: %s", exc)
            return None

    def _eth_value_above_threshold(self, value_wei: int, eth_price: float) -> bool:
        """Return True when a native ETH value meets the whale threshold.

        Args:
            value_wei: Transaction value in wei.
            eth_price: Current ETH/USD price.

        Returns:
            ``True`` if ``(value_wei / 1e18) * eth_price >= MIN_WHALE_USD``.
        """
        if eth_price <= 0 or value_wei <= 0:
            return False
        value_eth = Decimal(value_wei) / _ETH_DECIMALS
        value_usd = float(value_eth) * eth_price
        return value_usd >= self._settings.MIN_WHALE_USD

    def _token_value_above_threshold(
        self, amount: Decimal, token_symbol: str, eth_price: float
    ) -> bool:
        """Return True when a token transfer value meets the whale threshold.

        USDT and USDC are treated as 1:1 with USD.
        WETH is priced at the current ETH/USD rate.

        Args:
            amount: Token amount in human-readable units (post-decimals division).
            token_symbol: Token symbol string.
            eth_price: Current ETH/USD price.

        Returns:
            ``True`` if the USD equivalent is >= ``MIN_WHALE_USD``.
        """
        if token_symbol in ("USDT", "USDC"):
            value_usd = float(amount)
        elif token_symbol == "WETH":
            value_usd = float(amount) * eth_price
        else:
            return False
        return value_usd >= self._settings.MIN_WHALE_USD
