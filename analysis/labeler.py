"""Address labelling utilities using a hardcoded dictionary of known wallets."""

from __future__ import annotations

import logging

from web3 import Web3

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known wallet registry
# ---------------------------------------------------------------------------

KNOWN_WALLETS: dict[str, str] = {
    # Exchanges
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance Hot Wallet",
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance Cold Wallet",
    "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3": "Coinbase",
    "0x503828976D22510aad0201ac7EC88293211D23Da": "Coinbase 2",
    "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2": "Kraken",
    "0x0A869d79a7052C7f1b55a8EbabbEa3420F0D1E13": "Kraken 2",
    "0x6cC5F688a315f3dC28A7781717a9A798a59fDA7b": "OKX",
    "0xf89d7b9c864f589bbF53a82105107622B35EaA40": "Bybit",
    # DeFi
    "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D": "Uniswap V2 Router",
    "0xE592427A0AEce92De3Edee1F18E0157C05861564": "Uniswap V3 Router",
    "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2": "Aave V3 Pool",
    "0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3b": "Compound",
    "0x9759A6Ac90977b93B58547b4A71c78317f391A28": "MakerDAO",
    # Bridges
    "0x40ec5B33f54e0E8A33A975908C5BA1c14e5BbbDf": "Polygon Bridge",
    "0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a": "Arbitrum Bridge",
    # Stablecoins
    "0x5754284f345afc66a98fbB0a0Afe71e0F007B949": "Tether Treasury",
    "0x55FE002aeff02F77364de339a1292923A15844B8": "Circle (USDC)",
}

WALLET_CATEGORIES: dict[str, str] = {
    "Binance Hot Wallet": "exchange",
    "Binance Cold Wallet": "exchange",
    "Coinbase": "exchange",
    "Coinbase 2": "exchange",
    "Kraken": "exchange",
    "Kraken 2": "exchange",
    "OKX": "exchange",
    "Bybit": "exchange",
    "Uniswap V2 Router": "defi",
    "Uniswap V3 Router": "defi",
    "Aave V3 Pool": "defi",
    "Compound": "defi",
    "MakerDAO": "defi",
    "Polygon Bridge": "bridge",
    "Arbitrum Bridge": "bridge",
    "Tether Treasury": "stablecoin",
    "Circle (USDC)": "stablecoin",
}

# Build a normalised (lowercase) lookup for fast O(1) address resolution.
_KNOWN_WALLETS_LOWER: dict[str, str] = {k.lower(): v for k, v in KNOWN_WALLETS.items()}

# Derive the set of exchange labels once at import time for direction detection.
_EXCHANGE_LABELS: frozenset[str] = frozenset(
    label for label, cat in WALLET_CATEGORIES.items() if cat == "exchange"
)


def get_label(address: str) -> str:
    """Return the human-readable label for a known Ethereum address.

    The lookup is case-insensitive; unknown addresses return "Unknown Wallet".

    Args:
        address: Any valid Ethereum address string (checksummed or lowercase).

    Returns:
        The label string associated with the address, or "Unknown Wallet".
    """
    if not address:
        return "Unknown Wallet"
    try:
        checksum = Web3.to_checksum_address(address)
        return KNOWN_WALLETS.get(checksum, "Unknown Wallet")
    except Exception:
        logger.debug("Could not normalise address: %s", address)
        return "Unknown Wallet"


def get_category(label: str) -> str:
    """Return the category for a wallet label.

    Args:
        label: A wallet label string as returned by :func:`get_label`.

    Returns:
        The category string (exchange, defi, bridge, stablecoin) or "unknown".
    """
    return WALLET_CATEGORIES.get(label, "unknown")


def get_direction(from_label: str, to_label: str) -> str:
    """Determine the transaction direction based on address labels.

    Possible return values:

    * ``"from_exchange"``  — funds leaving an exchange (possible withdrawal/accumulation).
    * ``"to_exchange"``    — funds entering an exchange (possible sell).
    * ``"wallet_to_wallet"`` — neither address is a known exchange.

    Args:
        from_label: Label of the sending address.
        to_label:   Label of the receiving address.

    Returns:
        One of the three direction strings described above.
    """
    from_is_exchange = from_label in _EXCHANGE_LABELS
    to_is_exchange = to_label in _EXCHANGE_LABELS

    if from_is_exchange:
        return "from_exchange"
    if to_is_exchange:
        return "to_exchange"
    return "wallet_to_wallet"
