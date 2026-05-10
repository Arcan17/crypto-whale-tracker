# Crypto Whale Tracker

## On-Chain Intelligence Pipeline — Python, Web3.py, FastAPI, PostgreSQL, Dashboard & Telegram Alerts

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![CI](https://github.com/Arcan17/crypto-whale-tracker/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Ethereum](https://img.shields.io/badge/ethereum-mainnet-purple.svg)
![Telegram](https://img.shields.io/badge/alerts-telegram-26A5E4.svg)

Crypto Whale Tracker is a portfolio-grade on-chain intelligence pipeline for
monitoring high-value Ethereum transactions. It streams pending transactions with
Web3.py, detects transfers above a configurable USD threshold, labels known
exchange/DeFi/bridge wallets, stores alert history through SQLAlchemy
(SQLite locally, PostgreSQL-ready), exposes FastAPI analytics endpoints, renders
a lightweight browser dashboard, and can send Telegram whale alerts.

---

## Quickstart

These commands run the local demo path: seed deterministic whale transactions,
start the FastAPI API, open the dashboard, and run the test suite.

```bash
# 1) Clone repo
git clone https://github.com/Arcan17/crypto-whale-tracker.git
cd crypto-whale-tracker

# 2) Create an environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) Copy environment template
cp .env.example .env

# 4) Run demo seed data into the local SQLite database
python scripts/seed_demo.py

# 5) Start the API in one terminal
uvicorn api.main:app --host 0.0.0.0 --port 8080

# 6) Start the dashboard in a second terminal
python -m http.server 8000 --directory dashboard
# Open http://localhost:8000

# 7) Run tests
pytest tests/ -v
```

For live Ethereum monitoring and Telegram alerts, edit `.env` with a real
`ALCHEMY_WS_URL`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID`, then run:

```bash
python main.py
```

Docker is also available for the live application path:

```bash
cp .env.example .env
# Edit .env with live credentials, then:
docker-compose up --build
```

---

## How It Works

```text
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
      |
      +──> [Dashboard] browser UI over FastAPI JSON
```

---

## Example Telegram Alert

```text
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

| Component | Technology |
| --- | --- |
| Language | Python 3.11 |
| Ethereum feed | Web3.py + websockets |
| Price oracle | CoinGecko REST API, cached for 60 seconds |
| Database | SQLAlchemy 2.0, SQLite default, PostgreSQL-ready with psycopg |
| REST API | FastAPI + Uvicorn |
| Dashboard | Static HTML/CSS/JavaScript over FastAPI JSON endpoints |
| Alert delivery | python-telegram-bot v20 |
| Containerization | Docker / docker-compose |
| CI | GitHub Actions |
| Testing | pytest + pytest-asyncio |

---

## Configuration

All settings are loaded from environment variables or a local `.env` file.

| Variable | Description | Default |
| --- | --- | --- |
| `ALCHEMY_WS_URL` | Alchemy WebSocket endpoint for Ethereum Mainnet | `wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token from @BotFather | empty; alerts disabled |
| `TELEGRAM_CHAT_ID` | Chat or channel ID to receive whale alerts | empty; alerts disabled |
| `MIN_WHALE_USD` | Minimum USD value to trigger an alert | `500000` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./data/whales.db` |
| `HEALTH_PORT` | Port for the FastAPI server used by `python main.py` | `8080` |
| `LOG_LEVEL` | Python logging level | `INFO` |
| `MONITOR_TOKENS` | Comma-separated list of token symbols to monitor | `ETH,USDT,USDC,WETH` |

Example PostgreSQL setting:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/whales
```

---

## API Reference

Start the API for local seeded data:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8080
```

### `GET /health`

Returns application health and WebSocket connection status.

```bash
curl http://localhost:8080/health
```

```json
{
  "status": "healthy",
  "connected": false,
  "uptime_seconds": 12.34
}
```

### `GET /stats`

Returns aggregated statistics for the current UTC day.

```bash
curl http://localhost:8080/stats
```

```json
{
  "total_alerts_today": 3,
  "total_volume_usd_today": 2780000.0,
  "top_tokens": [
    {"symbol": "ETH", "count": 1},
    {"symbol": "USDC", "count": 1},
    {"symbol": "WETH", "count": 1}
  ],
  "last_alert_at": "2026-05-10T12:00:00"
}
```

### `GET /transactions?limit=20&skip=0&token=USDC`

Paginated list of stored whale transactions with an optional token filter.

```bash
curl "http://localhost:8080/transactions?limit=3&token=USDC"
```

---

### `GET /wallet/{address}/summary`

Wallet intelligence — aggregated stats for a specific Ethereum address.

```bash
curl "http://localhost:8080/wallet/0x28C6c06298d514Db089934071355E5743bf21d60/summary"
```

---

### `GET /wallet/{address}/transactions`

All transactions involving a specific wallet address.

```bash
curl "http://localhost:8080/wallet/0x28C6c06298d514Db089934071355E5743bf21d60/transactions"
```

---

### `GET /transactions/export.csv`

Download all stored transactions as a CSV file.

```bash
curl "http://localhost:8080/transactions/export.csv" -o transactions.csv
```

---

### `GET /transactions/export.xlsx`

Download all stored transactions as an Excel workbook.

```bash
curl "http://localhost:8080/transactions/export.xlsx" -o transactions.xlsx
```

```json
{
  "total": 1,
  "skip": 0,
  "limit": 3,
  "transactions": [
    {
      "id": 2,
      "tx_hash": "0xb2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2",
      "from_address": "0x2222222222222222222222222222222222222222",
      "from_label": "Unknown Wallet",
      "to_address": "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",
      "to_label": "Coinbase",
      "value_eth": "0E-8",
      "value_usd": "875000.00",
      "token_symbol": "USDC",
      "block_number": 19450456,
      "direction": "to_exchange",
      "created_at": "2026-05-10T12:00:00"
    }
  ]
}
```

---

## Dashboard

The dashboard is a dependency-free static UI that reads from the FastAPI API.
Run it after seeding data and starting the API:

```bash
python -m http.server 8000 --directory dashboard
```

Open `http://localhost:8000`. If your API is running somewhere else, pass the
base URL as a query parameter, for example:

```text
http://localhost:8000?api=http://localhost:8080
```

![Dashboard](docs/screenshots/dashboard.png)

---

## Project Structure

```text
crypto-whale-tracker/
├── main.py                  # Live application entry point
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
├── dashboard/
│   └── index.html           # Static portfolio dashboard
├── scripts/
│   └── seed_demo.py         # Deterministic local demo seed data
├── tests/
│   ├── conftest.py          # Shared fixtures and helpers
│   ├── test_filter.py       # TransactionFilter unit tests
│   └── test_labeler.py      # Labeler unit tests
├── data/                    # SQLite database directory (gitignored except .gitkeep)
├── ARCHITECTURE.md
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
pytest tests/ -v
```

Current expected result: **18 tests passing** (filter + labeler unit tests).

```text
collected 18 items
...
======================== 18 passed, 1 warning in 0.08s =========================
```

You can also run tests inside Docker:

```bash
docker-compose run --rm app pytest tests/ -v
```

---

## Portfolio Use Case

This project is designed to demonstrate production-adjacent Web3 data skills for
roles that require more than a basic CRUD application.

### Web3 Data Analyst

- Converts raw on-chain transfers into labeled, queryable whale events.
- Provides `/stats` and `/transactions` endpoints for volume, token, and wallet-flow analysis.
- Demonstrates exchange inflow/outflow interpretation through `from_exchange`, `to_exchange`, and `wallet_to_wallet` direction labels.

### Blockchain Data Engineer

- Shows a streaming ingestion pattern from Ethereum WebSockets into durable SQL storage.
- Uses SQLAlchemy models and environment-driven database URLs so the same code can run locally on SQLite or against PostgreSQL.
- Includes health checks, reconnect-oriented feed design, test coverage, Docker packaging, and CI-friendly commands.

### On-chain Analytics Developer

- Implements address intelligence with known exchange, DeFi, bridge, and stablecoin labels.
- Exposes API-ready analytics primitives that can power dashboards, alerting, or analyst workflows.
- Includes deterministic demo seed data so reviewers can inspect the API and dashboard without live credentials.

### Python Web3 Developer

- Uses asynchronous Python patterns around Web3.py, HTTP requests, FastAPI, and Telegram notifications.
- Separates feed ingestion, filtering, labeling, persistence, API, dashboard, and alert concerns into readable modules.
- Demonstrates practical testing of whale threshold logic, token transfer decoding, price caching, and address labels.

---

## Why This Project Matters for Crypto Jobs

Most backend developers can build CRUD APIs. Far fewer have worked directly with:

- **Live blockchain data** — streaming pending transactions via WebSocket.
- **On-chain address intelligence** — labeling wallets as exchanges, DeFi protocols, bridges, or stablecoin treasuries.
- **Low-latency event pipelines** — async components that detect, persist, expose, and alert on whale events.
- **Production trading and risk patterns** — health checks, audit trails, reconnect logic, demo data, dashboards, and tests.

The project maps to the workflows used by on-chain analytics firms, crypto
exchanges, DeFi protocols, and risk teams building real-time monitoring systems.

---

## Disclaimer

> This project is for **educational purposes only** and does not constitute financial advice.
> Monitoring on-chain data does not guarantee profitable trading decisions.
> Always do your own research.
