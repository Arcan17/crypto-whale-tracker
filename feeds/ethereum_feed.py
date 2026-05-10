"""Ethereum WebSocket feed — subscribes to pending transactions and processes them."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

import websockets
from web3 import AsyncWeb3

from analysis.filter import TransactionFilter, WhaleTransaction
from alerts.telegram_alert import TelegramAlert

logger = logging.getLogger(__name__)

_MAX_BACKOFF = 60  # seconds


class EthereumFeed:
    """Streams new pending transactions from an Ethereum node via WebSocket.

    Whenever a transaction is confirmed to be a whale event by
    :class:`~analysis.filter.TransactionFilter` the provided callback is
    invoked.

    Reconnection uses exponential backoff starting at 1 s up to ``_MAX_BACKOFF``
    seconds.

    Args:
        settings: Application settings instance.
        tx_filter: :class:`~analysis.filter.TransactionFilter` instance used to
            decide whether a transaction is whale-sized.
        alert: :class:`~alerts.telegram_alert.TelegramAlert` used to notify on
            whale detection.
        session_factory: SQLAlchemy ``SessionLocal`` callable for DB writes.
    """

    def __init__(
        self,
        settings: object,
        tx_filter: TransactionFilter,
        alert: TelegramAlert,
        session_factory: Callable,
    ) -> None:
        """Initialise the feed.

        Args:
            settings: Application :class:`~config.settings.Settings`.
            tx_filter: Transaction filter instance.
            alert: Telegram alert instance.
            session_factory: SQLAlchemy session factory (``SessionLocal``).
        """
        self._settings = settings
        self._tx_filter = tx_filter
        self._alert = alert
        self._session_factory = session_factory
        self._connected: bool = False

    @property
    def connected(self) -> bool:
        """Whether the feed is currently connected to the WebSocket endpoint."""
        return self._connected

    async def start(self) -> None:
        """Start the feed with exponential backoff reconnect logic.

        This coroutine runs indefinitely.  On each disconnect or error the
        wait time doubles (capped at ``_MAX_BACKOFF`` seconds) before the next
        reconnect attempt.
        """
        backoff = 1
        while True:
            try:
                logger.info("Connecting to Ethereum WebSocket feed…")
                await self._connect_and_subscribe()
                backoff = 1  # Reset on clean disconnect.
            except Exception as exc:
                self._connected = False
                logger.error("WebSocket feed error: %s — reconnecting in %s s", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _connect_and_subscribe(self) -> None:
        """Open a WebSocket connection, subscribe to new pending transactions,
        and dispatch incoming hashes for processing.

        Raises:
            websockets.exceptions.WebSocketException: On connection failures.
        """
        ws_url: str = self._settings.ALCHEMY_WS_URL
        http_url: str = ws_url.replace("wss://", "https://").replace("ws://", "http://")

        subscribe_msg = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["newPendingTransactions"],
            }
        )

        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=30) as ws:
            self._connected = True
            logger.info("WebSocket connected. Subscribing to pending transactions…")
            await ws.send(subscribe_msg)

            # Read subscription confirmation
            confirmation = await ws.recv()
            logger.debug("Subscription response: %s", confirmation)

            w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(http_url))

            async for raw_message in ws:
                try:
                    msg = json.loads(raw_message)
                    # Subscription notifications look like:
                    # {"jsonrpc":"2.0","method":"eth_subscription","params":{"result":"0x..."}}
                    params = msg.get("params")
                    if params is None:
                        continue
                    tx_hash = params.get("result")
                    if not isinstance(tx_hash, str):
                        continue
                    asyncio.ensure_future(self._process_tx_hash(tx_hash, w3))
                except Exception as exc:
                    logger.debug("Error processing message: %s", exc)

        self._connected = False

    async def _process_tx_hash(self, tx_hash: str, w3: AsyncWeb3) -> None:
        """Fetch a transaction + receipt and check whether it is a whale event.

        If the transaction qualifies the whale callback chain is invoked:
        DB persistence and Telegram notification.

        Args:
            tx_hash: Hex transaction hash to fetch.
            w3: Async web3 instance backed by HTTP provider.
        """
        try:
            tx = await w3.eth.get_transaction(tx_hash)  # type: ignore[arg-type]
            if tx is None:
                return
            receipt = await w3.eth.get_transaction_receipt(tx_hash)  # type: ignore[arg-type]
            if receipt is None:
                return

            # Convert AttributeDict → plain dict for easier handling.
            tx_dict = dict(tx)
            receipt_dict = dict(receipt)
            if "logs" in receipt_dict:
                receipt_dict["logs"] = [dict(log) for log in receipt_dict["logs"]]

            whale_tx: Optional[WhaleTransaction] = await self._tx_filter.analyze_transaction(
                tx_dict, receipt_dict
            )
            if whale_tx is not None:
                logger.info(
                    "Whale detected: %s $%.0f %s",
                    whale_tx.hash[:12],
                    whale_tx.value_usd,
                    whale_tx.token_symbol,
                )
                await self._on_whale_detected(whale_tx)

        except Exception as exc:
            logger.debug("Error processing tx %s: %s", tx_hash[:12], exc)

    async def _on_whale_detected(self, whale_tx: WhaleTransaction) -> None:
        """Persist whale transaction to DB and send Telegram alert.

        Skips DB write silently when the tx_hash is already present (idempotent).

        Args:
            whale_tx: The detected whale transaction.
        """
        from models.database import Transaction  # local import avoids circular deps

        try:
            session = self._session_factory()
            try:
                existing = session.query(Transaction).filter_by(tx_hash=whale_tx.hash).first()
                if existing is None:
                    record = Transaction(
                        tx_hash=whale_tx.hash,
                        from_address=whale_tx.from_address,
                        from_label=whale_tx.from_label,
                        to_address=whale_tx.to_address,
                        to_label=whale_tx.to_label,
                        value_eth=float(whale_tx.value_eth),
                        value_usd=whale_tx.value_usd,
                        token_symbol=whale_tx.token_symbol,
                        block_number=whale_tx.block_number,
                        direction=whale_tx.direction,
                    )
                    session.add(record)
                    session.commit()
                    logger.debug("Saved whale tx %s to DB.", whale_tx.hash[:12])
            except Exception as db_exc:
                session.rollback()
                logger.error("DB write failed for %s: %s", whale_tx.hash[:12], db_exc)
            finally:
                session.close()
        except Exception as exc:
            logger.error("Session error: %s", exc)

        try:
            await self._alert.send_whale_alert(whale_tx)
        except Exception as exc:
            logger.error("Telegram alert failed for %s: %s", whale_tx.hash[:12], exc)
