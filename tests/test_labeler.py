"""Tests for analysis.labeler — address labelling and direction detection."""

from analysis.labeler import (
    get_category,
    get_direction,
    get_label,
)

# ---------------------------------------------------------------------------
# Known addresses used across tests
# ---------------------------------------------------------------------------

BINANCE_HOT = "0x28C6c06298d514Db089934071355E5743bf21d60"
COINBASE = "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3"
UNKNOWN_ADDR = "0x1111111111111111111111111111111111111111"
UNISWAP_V2 = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
ARBITRUM_BRIDGE = "0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a"
TETHER_TREASURY = "0x5754284f345afc66a98fbB0a0Afe71e0F007B949"


# ---------------------------------------------------------------------------
# 1. Known exchange address returns its label
# ---------------------------------------------------------------------------


def test_known_exchange_address_returns_label():
    """get_label must return the correct label for a known exchange address."""
    label = get_label(BINANCE_HOT)
    assert label == "Binance Hot Wallet"


# ---------------------------------------------------------------------------
# 2. Unknown address returns "Unknown Wallet"
# ---------------------------------------------------------------------------


def test_unknown_address_returns_unknown_wallet():
    """get_label must return "Unknown Wallet" for an address not in the registry."""
    label = get_label(UNKNOWN_ADDR)
    assert label == "Unknown Wallet"


# ---------------------------------------------------------------------------
# 3. Direction "from_exchange" is detected when sender is an exchange
# ---------------------------------------------------------------------------


def test_direction_from_exchange_detected():
    """get_direction must return "from_exchange" when the sender is a known exchange."""
    from_label = get_label(BINANCE_HOT)  # "Binance Hot Wallet"
    to_label = get_label(UNKNOWN_ADDR)  # "Unknown Wallet"
    direction = get_direction(from_label, to_label)
    assert direction == "from_exchange"


# ---------------------------------------------------------------------------
# 4. Direction "to_exchange" is detected when recipient is an exchange
# ---------------------------------------------------------------------------


def test_direction_to_exchange_detected():
    """get_direction must return "to_exchange" when the recipient is a known exchange."""
    from_label = get_label(UNKNOWN_ADDR)  # "Unknown Wallet"
    to_label = get_label(COINBASE)  # "Coinbase"
    direction = get_direction(from_label, to_label)
    assert direction == "to_exchange"


# ---------------------------------------------------------------------------
# 5. Direction "wallet_to_wallet" when neither side is an exchange
# ---------------------------------------------------------------------------


def test_direction_wallet_to_wallet_detected():
    """get_direction must return "wallet_to_wallet" when neither address is an exchange."""
    from_label = get_label(UNISWAP_V2)  # "Uniswap V2 Router" (defi)
    to_label = get_label(UNKNOWN_ADDR)  # "Unknown Wallet"
    direction = get_direction(from_label, to_label)
    assert direction == "wallet_to_wallet"


# ---------------------------------------------------------------------------
# 6. get_category returns "exchange" for exchange labels
# ---------------------------------------------------------------------------


def test_get_category_exchange():
    """get_category must return "exchange" for known exchange labels."""
    label = get_label(BINANCE_HOT)
    category = get_category(label)
    assert category == "exchange"


# ---------------------------------------------------------------------------
# 7. get_category returns "unknown" for unlabelled wallets
# ---------------------------------------------------------------------------


def test_get_category_unknown_returns_unknown():
    """get_category must return "unknown" for labels not in WALLET_CATEGORIES."""
    category = get_category("Unknown Wallet")
    assert category == "unknown"


# ---------------------------------------------------------------------------
# 8. Lowercase address lookup works (case-insensitive)
# ---------------------------------------------------------------------------


def test_lowercase_address_lookup():
    """get_label must resolve lowercase addresses to the correct label."""
    label = get_label(BINANCE_HOT.lower())
    assert label == "Binance Hot Wallet"


# ---------------------------------------------------------------------------
# 9. get_category returns "stablecoin" for stablecoin labels
# ---------------------------------------------------------------------------


def test_get_category_stablecoin():
    """get_category must return "stablecoin" for the Tether Treasury label."""
    label = get_label(TETHER_TREASURY)
    assert label == "Tether Treasury"
    category = get_category(label)
    assert category == "stablecoin"


# ---------------------------------------------------------------------------
# 10. get_category returns "bridge" for bridge labels
# ---------------------------------------------------------------------------


def test_get_category_bridge():
    """get_category must return "bridge" for the Arbitrum Bridge label."""
    label = get_label(ARBITRUM_BRIDGE)
    assert label == "Arbitrum Bridge"
    category = get_category(label)
    assert category == "bridge"
