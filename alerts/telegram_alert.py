"""Telegram alert sender for whale transaction notifications."""

from __future__ import annotations

import logging
import re

from telegram import Bot
from telegram.constants import ParseMode

from analysis.filter import WhaleTransaction

logger = logging.getLogger(__name__)

# Characters that must be escaped in MarkdownV2 (outside code spans).
_MDV2_SPECIAL = r"\_*[]()~`>#+-=|{}.!"


def _escape_mdv2(text: str) -> str:
    """Escape all MarkdownV2 special characters in *text*.

    Args:
        text: Raw text that may contain MarkdownV2 special characters.

    Returns:
        Escaped text safe to embed in a MarkdownV2 Telegram message.
    """
    return re.sub(r"([_\*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)


def _short_address(address: str) -> str:
    """Return a condensed address representation.

    Args:
        address: Full Ethereum address string.

    Returns:
        String in the form ``0x1234...abcd``.
    """
    if not address or len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"


_DIRECTION_HINTS: dict[str, str] = {
    "from_exchange": "Possible withdrawal/accumulation",
    "to_exchange": "Possible sell",
    "wallet_to_wallet": "Whale\\-to\\-whale transfer",
}


class TelegramAlert:
    """Sends formatted whale alert messages to a Telegram chat.

    Args:
        settings: Application :class:`~config.settings.Settings` instance.
    """

    def __init__(self, settings: object) -> None:
        """Initialise the Telegram bot client.

        Args:
            settings: Application settings containing bot token and chat ID.
        """
        self._settings = settings
        self._bot: Bot | None = None
        if settings.TELEGRAM_BOT_TOKEN:
            self._bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    async def send_whale_alert(self, whale_tx: WhaleTransaction) -> None:
        """Send a MarkdownV2-formatted whale alert to the configured Telegram chat.

        Silently skips sending when ``TELEGRAM_BOT_TOKEN`` or
        ``TELEGRAM_CHAT_ID`` is not configured.

        Args:
            whale_tx: The :class:`~analysis.filter.WhaleTransaction` to report.
        """
        if self._bot is None or not self._settings.TELEGRAM_CHAT_ID:
            logger.debug("Telegram not configured — skipping alert for %s.", whale_tx.hash[:12])
            return

        try:
            message = self._format_message(whale_tx)
            await self._bot.send_message(
                chat_id=self._settings.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
            )
            logger.info("Telegram alert sent for tx %s.", whale_tx.hash[:12])
        except Exception as exc:
            logger.error("Failed to send Telegram alert: %s", exc)

    def _format_message(self, whale_tx: WhaleTransaction) -> str:
        """Build a MarkdownV2 alert message string.

        Args:
            whale_tx: The whale transaction data.

        Returns:
            A fully escaped MarkdownV2 string ready to send via the Bot API.
        """
        value_usd_str = _escape_mdv2(f"${whale_tx.value_usd:,.0f}")
        token_str = _escape_mdv2(whale_tx.token_symbol)
        from_label_str = _escape_mdv2(whale_tx.from_label)
        to_label_str = _escape_mdv2(whale_tx.to_label)
        short_addr = _escape_mdv2(_short_address(whale_tx.to_address or ""))
        gas_str = _escape_mdv2(f"{whale_tx.gas_used:,}")
        block_str = _escape_mdv2(f"{whale_tx.block_number:,}")
        tx_url = f"https://etherscan\\.io/tx/{whale_tx.hash}"

        direction_hint = _DIRECTION_HINTS.get(whale_tx.direction, "")
        if direction_hint and not direction_hint.endswith("\\-to\\-whale transfer"):
            direction_hint = _escape_mdv2(direction_hint)

        hint_line = f"\n💡 {direction_hint}" if direction_hint else ""

        return (
            f"🐋 *WHALE ALERT*\n"
            f"\n"
            f"💰 {value_usd_str} {token_str}\n"
            f"📤 From: {from_label_str}\n"
            f"📥 To: {to_label_str} \\({short_addr}\\)\n"
            f"⛽ Gas: {gas_str} \\| Block: \\#{block_str}\n"
            f"🔗 {tx_url}"
            f"{hint_line}"
        )
