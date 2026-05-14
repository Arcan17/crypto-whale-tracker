# Crypto Whale Tracker

**Real-time Ethereum on-chain intelligence pipeline with Telegram alerts and REST API.**

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![Tests](https://img.shields.io/badge/tests-30%20passing-brightgreen)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![CI](https://github.com/Arcan17/crypto-whale-tracker/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Ethereum](https://img.shields.io/badge/ethereum-mainnet-purple.svg)
![Telegram](https://img.shields.io/badge/alerts-telegram-26A5E4.svg)

---

## The Problem

Ethereum processes thousands of pending transactions per minute. Most are small — but a handful move millions of dollars across exchanges, DeFi protocols, and anonymous wallets.

These **whale movements** are signals: large inflows to exchanges may indicate selling pressure; outflows suggest accumulation. But monitoring them in real time requires:

- A persistent WebSocket connection to an Ethereum node
- Decoding raw ERC-20 Transfer logs to get token amounts
- Converting on-chain values to USD in real time
- Knowing which wallet addresses belong to Binance, Coinbase, Uniswap, etc.

This project does all of that — automatically.

## The Solution

Crypto Whale Tracker streams every pending Ethereum transaction, filters for transfers above a configurable USD threshold (default: **$500,000**), labels the wallets involved, stores the alert in a database, and sends an instant Telegram notification.

All data is queryable through a FastAPI REST API with pagination, CSV/Excel export, and wallet intelligence summaries.

---

## Dashboard

![Dashboard](docs/screenshots/dashboard.png)

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

## Features

- **Real-time WebSocket streaming** — subscribes to `newPendingTransactions` via Alchemy
- **ETH + ERC-20 detection** — native ETH and USDT/USDC/WETH token transfers
- **USD threshold filtering** — configurable minimum (default: $500,000)
- **Wallet intelligence** — labels 17+ known wallets (Binance, Coinbase, Uniswap, etc.)
- **Direction classification** — `from_exchange`, `to_exchange`, `wallet_to_wallet`
- **Telegram notifications** — instant MarkdownV2 alerts via python-telegram-bot
- **PostgreSQL-ready** — SQLite locally, swap `DATABASE_URL` for production
- **FastAPI REST API** — paginated queries, wallet summaries, CSV/XLSX export
- **Browser dashboard** — static HTML/JS UI over the FastAPI endpoints
- **30 passing tests** — filter logic, labeler, API endpoints, wallet intelligence, exports
- **Auto-reconnect** — exponential backoff WebSocket reconnection (1s → 60s max)
- **Docker + CI/CD** — one command deploy, GitHub Actions on every push

---

## Architecture

```
Ethereum Mainnet (pending transactions)
         │
         │  WebSocket — eth_subscribe → newPendingTransactions
         ▼
[EthereumFeed]          feeds/ethereum_feed.py
  ├─ WebSocket connection (Alchemy)
  ├─ Exponential backoff reconnect
  └─ Fire-and-forget coroutine per tx hash
         │
         │  tx_hash → fetch tx + receipt (web3.py AsyncHTTP)
         ▼
[TransactionFilter]     analysis/filter.py
  ├─ Native ETH: value_wei × eth_price ≥ threshold?
  ├─ ERC-20: decode Transfer logs → USDT/USDC/WETH amount?
  └─ ETH/USD price via CoinGecko (cached 60s)
         │
         │  whale detected (≥ MIN_WHALE_USD)
         ▼
[Labeler]               analysis/labeler.py
  ├─ address → known label (O(1) dict lookup)
  └─ direction → from_exchange / to_exchange / wallet_to_wallet
         │
    ┌────┴────┐
    ▼         ▼
[Database]   [TelegramAlert]
SQLAlchemy   MarkdownV2 message
SQLite/PG    python-telegram-bot
    │
    ▼
[FastAPI]               api/main.py
  GET /health
  GET /stats
  GET /transactions
  GET /transactions/export.csv
  GET /transactions/export.xlsx
  GET /wallet/{address}/summary
  GET /wallet/{address}/transactions
    │
    ▼
[Dashboard]             dashboard/index.html
Static HTML/JS — reads from FastAPI
```

---

## Tech Stack

| Component        | Technology                                  |
|------------------|---------------------------------------------|
| Language         | Python 3.11                                 |
| Ethereum feed    | Web3.py + websockets                        |
| Price oracle     | CoinGecko REST API (cached 60s)             |
| Database         | SQLAlchemy 2.0 — SQLite (local) / PostgreSQL |
| REST API         | FastAPI + Uvicorn                           |
| Dashboard        | Static HTML/CSS/JS                          |
| Alert delivery   | python-telegram-bot v20                     |
| Containerization | Docker + Docker Compose                     |
| CI/CD            | GitHub Actions                              |
| Testing          | pytest + pytest-asyncio (30 tests)          |

---

## Quickstart (Local Demo)

No Alchemy key needed — uses seeded demo data.

```bash
git clone https://github.com/Arcan17/crypto-whale-tracker.git
cd crypto-whale-tracker

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env

# 1. Seed demo data
python scripts/seed_demo.py

# 2. Start the API
uvicorn api.main:app --host 0.0.0.0 --port 8080

# 3. Open the dashboard (new terminal)
python -m http.server 8000 --directory dashboard
# Visit http://localhost:8000

# 4. Run tests
pytest tests/ -v
```

---

## Live Monitoring (Alchemy + Telegram)

```bash
cp .env.example .env
# Edit .env — see Environment Variables below

python main.py
# or
docker-compose up --build
```

---

## Environment Variables

```bash
cp .env.example .env
```

| Variable             | Description                                         | Default                                          |
|----------------------|-----------------------------------------------------|--------------------------------------------------|
| `ALCHEMY_WS_URL`     | Alchemy WebSocket endpoint for Ethereum Mainnet     | `wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY`    |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token from @BotFather             | *(empty — alerts disabled)*                      |
| `TELEGRAM_CHAT_ID`   | Chat or channel ID to receive alerts                | *(empty — alerts disabled)*                      |
| `MIN_WHALE_USD`      | Minimum USD value to trigger an alert               | `500000`                                         |
| `DATABASE_URL`       | SQLAlchemy connection string                        | `sqlite:///./data/whales.db`                     |
| `HEALTH_PORT`        | Port for the FastAPI server                         | `8080`                                           |
| `LOG_LEVEL`          | Python logging level                                | `INFO`                                           |
| `MONITOR_TOKENS`     | Comma-separated token symbols to monitor            | `ETH,USDT,USDC,WETH`                             |

**Getting a free Alchemy key:**
1. Sign up at [alchemy.com](https://alchemy.com)
2. Create app → Ethereum Mainnet
3. Copy the WebSocket URL into `ALCHEMY_WS_URL`

**PostgreSQL:**
```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/whales
```

---

## REST API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8080
# Interactive docs: http://localhost:8080/docs
```

| Method | Endpoint                          | Description                              |
|--------|-----------------------------------|------------------------------------------|
| `GET`  | `/health`                         | App status + WebSocket connection state  |
| `GET`  | `/stats`                          | Today's alerts, volume, top tokens       |
| `GET`  | `/transactions`                   | Paginated whale transactions             |
| `GET`  | `/transactions/export.csv`        | Download as CSV                          |
| `GET`  | `/transactions/export.xlsx`       | Download as Excel                        |
| `GET`  | `/wallet/{address}/summary`       | Wallet intelligence + volume stats       |
| `GET`  | `/wallet/{address}/transactions`  | All transactions for a wallet            |

```bash
curl http://localhost:8080/health
curl "http://localhost:8080/transactions?limit=10&token=USDC&min_usd=1000000"
curl "http://localhost:8080/wallet/0x28C6c06298d514Db089934071355E5743bf21d60/summary"
curl "http://localhost:8080/transactions/export.csv" -o whales.csv
```

<details>
<summary>Sample responses</summary>

**GET /health**
```json
{ "status": "healthy", "connected": true, "uptime_seconds": 3612.5 }
```

**GET /stats**
```json
{
  "total_alerts_today": 12,
  "total_volume_usd_today": 14500000.0,
  "top_tokens": [{"symbol": "USDC", "count": 5}, {"symbol": "ETH", "count": 4}],
  "last_alert_at": "2024-05-10T14:23:01"
}
```
</details>

---

## Running Tests

```bash
pytest tests/ -v
```

```
tests/test_filter.py          8 passed   ← whale detection logic
tests/test_labeler.py        10 passed   ← address labeling
tests/test_api.py             6 passed   ← API endpoints
tests/test_api_exports.py     3 passed   ← CSV/XLSX export
tests/test_wallet_api.py      3 passed   ← wallet intelligence endpoints
──────────────────────────────────────────
30 passed in 0.44s
```

All tests use mocks — no Alchemy API key or Telegram token required.

---

## Project Structure

```
crypto-whale-tracker/
├── main.py                  # Entry point: feed + API + alerts
├── config/
│   └── settings.py          # Pydantic Settings — env var config
├── feeds/
│   └── ethereum_feed.py     # WebSocket feed + reconnect logic
├── analysis/
│   ├── filter.py            # Whale detection + ERC-20 decoding
│   └── labeler.py           # Address → label/category/direction
├── alerts/
│   └── telegram_alert.py    # MarkdownV2 Telegram notifications
├── models/
│   └── database.py          # SQLAlchemy ORM + session factory
├── api/
│   └── main.py              # FastAPI: health, stats, transactions, wallet, exports
├── dashboard/
│   └── index.html           # Static browser dashboard
├── scripts/
│   └── seed_demo.py         # Deterministic demo data (no live credentials needed)
├── tests/
│   ├── conftest.py
│   ├── test_filter.py
│   ├── test_labeler.py
│   ├── test_api.py
│   ├── test_api_exports.py
│   └── test_wallet_api.py
├── ARCHITECTURE.md          # Deep technical documentation
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .github/workflows/ci.yml
```

---

## Technical Decisions

**Why `asyncio.ensure_future` instead of `await` per tx?**
Ethereum mainnet can push 100–500 tx hashes per second. Awaiting each fetch would block the WebSocket reader. `ensure_future` fires independent coroutines — the WebSocket stays responsive at any tx volume.

**Why SQLite by default?**
Zero-config local development. The same codebase switches to PostgreSQL with a single env var change (`DATABASE_URL`). For portfolio reviewers: no Docker PostgreSQL setup needed to run tests.

**Why CoinGecko with 60s cache?**
Each transaction check would otherwise require an HTTP round trip. At 200 tx/sec, that's 200 API calls/sec — CoinGecko's free tier limit is 50 calls/min. The 60s cache reduces this to 1 call/min with minimal price staleness.

**Why web3.py AsyncHTTP for tx fetching (not WebSocket)?**
Alchemy requires a split: WebSocket for subscriptions (`newPendingTransactions`), HTTP for individual data fetches. Both share the same API key.

---

## Known Limitations

- **Pending tx may drop** — a tx hash received via WebSocket may never be mined (MEV, gas too low). These are silently ignored when the fetch returns None.
- **ERC-20 scope** — only USDT, USDC, and WETH are decoded. Other tokens (DAI, LINK, etc.) require adding entries to `KNOWN_TOKENS`.
- **No historical backfill** — only monitors live transactions; no indexing of past blocks.
- **17 known wallets** — labeling coverage is limited to the hardcoded registry. Integrate Etherscan Labels or Nansen API for broader coverage.
- **Single chain** — Ethereum mainnet only. Polygon/Arbitrum/BSC would require separate feed instances.

---

## Roadmap

- [ ] Deploy live demo with seeded data (Render / Railway)
- [ ] Expand `KNOWN_TOKENS` to DAI, LINK, WBTC
- [ ] PostgreSQL migration for production deployment
- [ ] Webhook support: Discord, Slack
- [ ] On-chain labeling API integration (Etherscan, Nansen)
- [ ] Multi-chain feeds (Polygon, Arbitrum, BNB Chain)
- [ ] Frontend dashboard in React/Next.js

---

## Use Cases

This project demonstrates patterns used by:

- **Crypto exchanges** — real-time large transaction monitoring and risk alerts
- **DeFi protocols** — whale wallet tracking for liquidity event detection
- **On-chain analytics firms** — address labeling and flow intelligence pipelines
- **Trading desks** — exchange inflow/outflow signals for market direction

Adaptable for any EVM chain, any USD threshold, and any delivery channel (Telegram, Discord, email, webhook).

---

## Disclaimer

> This project is for **educational and portfolio purposes only** and does not constitute financial advice.
> Monitoring on-chain data does not guarantee profitable trading decisions.

---

## License

MIT
