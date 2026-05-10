# On-Chain Intelligence Pipeline

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![CI](https://github.com/Arcan17/crypto-whale-tracker/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Ethereum](https://img.shields.io/badge/ethereum-mainnet-purple.svg)
![Telegram](https://img.shields.io/badge/alerts-telegram-26A5E4.svg)

**Real-time Ethereum whale monitoring, wallet intelligence, REST API, dashboard-ready analytics and Telegram alerts built with Python, Web3.py, FastAPI and PostgreSQL.**

This repository is positioned as a Web3/Data Engineering portfolio project: an on-chain intelligence pipeline that ingests Ethereum mempool activity, enriches high-value transfers with price and wallet metadata, persists alert-ready records, and exposes analytics through an API that can power dashboards or downstream monitoring workflows.

The application keeps the original `crypto-whale-tracker` repository name while presenting the system as a production-style ETL pipeline for real-time blockchain data.

---

## What This Project Demonstrates

- **Real-time data ingestion:** subscribes to Ethereum pending transactions over WebSocket and recovers from connection interruptions.
- **On-chain event detection:** identifies whale-sized ETH and token transfers using a configurable USD threshold.
- **Data enrichment:** converts raw chain values into USD terms, adds wallet labels, and infers transfer direction such as exchange inflow or withdrawal.
- **Operational persistence:** stores normalized transaction records through SQLAlchemy using SQLite by default and PostgreSQL-compatible configuration for production-style deployments.
- **Analytics access layer:** provides FastAPI endpoints for health checks, daily aggregate statistics, and paginated transaction history.
- **Alerting workflow:** routes high-signal whale events to Telegram while retaining the same records for API queries and dashboards.

---

## Web3/Data Skills Demonstrated

| Skill Area | Demonstrated By |
|------------|-----------------|
| Web3 ingestion | Ethereum mempool subscription with WebSocket and transaction/receipt retrieval through Web3.py |
| On-chain analytics | Whale threshold filtering, token detection, wallet labeling, and flow-direction classification |
| ETL design | Extract from Ethereum, transform with pricing and labels, load into a relational store, and serve through APIs/alerts |
| Data modeling | SQLAlchemy ORM models for alert history and queryable transaction records |
| API engineering | FastAPI service exposing operational health, aggregate stats, and filtered historical data |
| Data operations | Environment-based configuration, Dockerized runtime, reconnect logic, logging, and CI-backed tests |

---

## Architecture: On-Chain ETL/Data Pipeline

```
                 EXTRACT
┌──────────────────────────────────────┐
│ Ethereum Mainnet                     │
│ newPendingTransactions WebSocket     │
└──────────────────┬───────────────────┘
                   │ pending tx hashes
                   v
┌──────────────────────────────────────┐
│ EthereumFeed                         │
│ reconnect loop + tx/receipt fetch    │
│ via Web3.py AsyncHTTP                │
└──────────────────┬───────────────────┘
                   │ raw transaction payloads
                   v
                TRANSFORM
┌──────────────────────────────────────┐
│ TransactionFilter                    │
│ token parsing + USD threshold checks │
│ CoinGecko ETH price cache            │
└──────────────────┬───────────────────┘
                   │ whale candidates
                   v
┌──────────────────────────────────────┐
│ Labeler                              │
│ known-wallet enrichment              │
│ exchange/DeFi/unknown categorization │
│ inflow/outflow direction inference   │
└──────────────────┬───────────────────┘
                   │ enriched whale events
                   v
                  LOAD / SERVE
┌──────────────────────────────────────┐
│ Database                             │
│ SQLAlchemy ORM                       │
│ SQLite default / PostgreSQL-ready    │
└──────────────┬───────────────────────┘
               │ persisted alert facts
       ┌───────┴────────┬──────────────────────┐
       v                v                      v
┌──────────────┐  ┌──────────────┐      ┌──────────────┐
│ FastAPI      │  │ Telegram Bot │      │ Dashboards / │
│ REST API     │  │ Alerts       │      │ BI consumers │
│ /health      │  │ high-signal  │      │ via API      │
│ /stats       │  │ notifications│      │              │
│ /transactions│  │              │      │              │
└──────────────┘  └──────────────┘      └──────────────┘
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

```bash
curl http://localhost:8081/stats
```

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

```bash
curl "http://localhost:8081/transactions?limit=3&token=USDC"
```

```json
{
  "total": 142,
  "skip": 0,
  "limit": 3,
  "transactions": [
    {
      "id": 142,
      "tx_hash": "0x3f4a1c2b8e9d0f5a7b6c3e2d1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2",
      "from_address": "0x28C6c06298d514Db089934071355E5743bf21d60",
      "from_label": "Binance Hot Wallet",
      "to_address": "0x9f3a4b2c1d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a",
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

## Why This Project Matters for Crypto Jobs

Most backend developers can build CRUD APIs. Far fewer have worked directly with:

- **Live blockchain data** — streaming thousands of pending transactions per second via WebSocket
- **on-chain address intelligence** — labeling wallets as exchanges, DeFi protocols, or bridges
- **Low-latency event pipelines** — fire-and-forget coroutines keeping detection under 700ms
- **Production trading infrastructure patterns** — health checks, audit trails, reconnect logic

This project demonstrates the exact skills used by teams at on-chain analytics firms (Nansen, Arkham), crypto exchanges, and DeFi protocols building real-time monitoring and risk systems.

---

## Disclaimer

> This project is for **educational purposes only** and does not constitute financial advice.
> Monitoring on-chain data does not guarantee profitable trading decisions.
> Always do your own research.
