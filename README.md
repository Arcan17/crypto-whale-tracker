# Crypto Whale Tracker

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![CI](https://github.com/Arcan17/crypto-whale-tracker/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Ethereum](https://img.shields.io/badge/ethereum-mainnet-purple.svg)
![Telegram](https://img.shields.io/badge/alerts-telegram-26A5E4.svg)

Real-time Ethereum whale transaction monitor.  Streams pending transactions via
WebSocket, detects transfers above a configurable USD threshold, labels addresses
against a registry of known exchanges and DeFi protocols, and fires instant
Telegram alerts — all while exposing a REST API for querying history.

---

## How It Works

```
Ethereum Network
      |
      | WebSocket (newPendingTransactions)
      v
[EthereumFeed] ──fetch tx+receipt──> [web3.py AsyncHTTP]
      |
      v
[TransactionFilter] ──ETH price──> [CoinGecko API]
      |
      | whale detected (>= $500k)
      v
[Labeler] ──label addresses──> known wallets dict
      |
      +──> [Database] SQLite/PostgreSQL (SQLAlchemy)
      |
      +──> [TelegramAlert] ──> Telegram Bot API
      |
      +──> [FastAPI] /health /stats /transactions
```

---

## Example Telegram Alert

```
🐋 WHALE ALERT

💰 $1,200,000 USDC
📤 From: Binance Hot Wallet
📥 To: Unknown Wallet (0x9f3a...b12c)
⛽ Gas: 65,000 | Block: #19,450,123
🔗 https://etherscan.io/tx/0xabc...def

💡 Possible withdrawal/accumulation
```

---

## Tech Stack

| Component         | Technology                        |
|-------------------|-----------------------------------|
| Language          | Python 3.11                       |
| Ethereum feed     | websockets + web3.py AsyncHTTP    |
| Price oracle      | CoinGecko REST API (cached 60 s)  |
| Database          | SQLAlchemy 2.0 / SQLite (default) |
| Alert delivery    | python-telegram-bot v20           |
| REST API          | FastAPI + Uvicorn                 |
| Containerisation  | Docker / docker-compose           |
| CI                | GitHub Actions                    |
| Testing           | pytest + pytest-asyncio           |

---

## Getting Started

### Docker (recommended)

```bash
git clone https://github.com/Arcan17/crypto-whale-tracker.git
cd crypto-whale-tracker
cp .env.example .env
# Edit .env with your Alchemy key, Telegram token, and chat ID
docker-compose up --build
```

### Local (virtualenv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env
python main.py
```

---

## Configuration

All settings are loaded from environment variables (or a `.env` file).

| Variable            | Description                                         | Default                                         |
|---------------------|-----------------------------------------------------|-------------------------------------------------|
| `ALCHEMY_WS_URL`    | Alchemy WebSocket endpoint for Ethereum Mainnet     | `wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY`  |
| `TELEGRAM_BOT_TOKEN`| Telegram Bot API token from @BotFather              | *(empty — alerts disabled)*                    |
| `TELEGRAM_CHAT_ID`  | Chat or channel ID to receive whale alerts          | *(empty — alerts disabled)*                    |
| `MIN_WHALE_USD`     | Minimum USD value to trigger an alert               | `500000`                                        |
| `DATABASE_URL`      | SQLAlchemy connection string                        | `sqlite:///./data/whales.db`                    |
| `HEALTH_PORT`       | Port for the FastAPI server                         | `8080`                                          |
| `LOG_LEVEL`         | Python logging level                                | `INFO`                                          |
| `MONITOR_TOKENS`    | Comma-separated list of token symbols to monitor    | `ETH,USDT,USDC,WETH`                            |

---

## API Reference

### `GET /health`

Returns application health and WebSocket connection status.

```json
{
  "status": "healthy",
  "connected": true,
  "uptime_seconds": 3612.45
}
```

### `GET /stats`

Returns aggregated statistics for the current UTC day.

```json
{
  "total_alerts_today": 14,
  "total_volume_usd_today": 23500000.00,
  "top_tokens": [
    {"symbol": "USDC", "count": 7},
    {"symbol": "ETH",  "count": 5},
    {"symbol": "WETH", "count": 2}
  ],
  "last_alert_at": "2026-05-01T14:23:01.000000"
}
```

### `GET /transactions?limit=20&skip=0&token=USDC`

Paginated list of stored whale transactions with optional token filter.

```json
{
  "total": 142,
  "skip": 0,
  "limit": 20,
  "transactions": [
    {
      "id": 142,
      "tx_hash": "0xabc...def",
      "from_address": "0x28C6...1d60",
      "from_label": "Binance Hot Wallet",
      "to_address": "0x9f3a...b12c",
      "to_label": "Unknown Wallet",
      "value_eth": "400.00000000",
      "value_usd": "1200000.00",
      "token_symbol": "USDC",
      "block_number": 19450123,
      "direction": "from_exchange",
      "created_at": "2026-05-01T14:23:01"
    }
  ]
}
```

---

## Project Structure

```
crypto-whale-tracker/
├── main.py                  # Application entry point
├── config/
│   └── settings.py          # Environment-variable configuration
├── feeds/
│   └── ethereum_feed.py     # WebSocket feed with reconnect logic
├── analysis/
│   ├── filter.py            # Whale detection and USD conversion
│   └── labeler.py           # Address → label/category/direction mapping
├── alerts/
│   └── telegram_alert.py    # MarkdownV2 Telegram notifications
├── models/
│   └── database.py          # SQLAlchemy ORM models + session factory
├── api/
│   └── main.py              # FastAPI endpoints (/health /stats /transactions)
├── tests/
│   ├── conftest.py          # Shared fixtures and helpers
│   ├── test_filter.py       # TransactionFilter unit tests
│   └── test_labeler.py      # Labeler unit tests
├── data/                    # SQLite database directory (gitignored except .gitkeep)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── .env.example
└── .gitignore
```

---

## Running Tests

```bash
# With virtualenv active
pytest tests/ -v

# Or via docker
docker-compose run --rm app pytest tests/ -v
```

Expected output (all passing):

```
tests/test_filter.py::test_eth_transaction_above_threshold_is_detected  PASSED
tests/test_filter.py::test_eth_transaction_below_threshold_is_ignored   PASSED
tests/test_filter.py::test_token_transfer_usdc_detected                  PASSED
...
tests/test_labeler.py::test_known_exchange_address_returns_label         PASSED
...
18 passed in 0.XXs
```

---

## Disclaimer

> This project is for **educational purposes only** and does not constitute financial advice.
> Monitoring on-chain data does not guarantee profitable trading decisions.
> Always do your own research.
