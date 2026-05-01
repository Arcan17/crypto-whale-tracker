# Architecture — Crypto Whale Tracker

## Overview

Crypto Whale Tracker is a real-time Ethereum monitoring system that streams pending transactions via WebSocket, identifies large ("whale") transfers above a configurable USD threshold, labels addresses against a registry of known exchanges and DeFi protocols, and delivers instant Telegram alerts. All detected transactions are persisted to a database and queryable through a REST API.

```
┌──────────────────────────────────────────────────┐
│               Ethereum Mainnet                   │
│  (thousands of pending transactions per minute)  │
└──────────────────┬───────────────────────────────┘
                   │ WebSocket (eth_subscribe)
                   │ newPendingTransactions
                   ▼
┌──────────────────────────────────┐
│  feeds/ethereum_feed.py          │
│  EthereumFeed                    │
│  ├─ WebSocket connection         │
│  ├─ Exponential backoff reconnect│
│  └─ Dispatches tx hashes async   │
└──────────────────┬───────────────┘
                   │ tx_hash → fetch tx + receipt
                   │ (web3.py AsyncHTTP)
                   ▼
┌──────────────────────────────────┐     ┌──────────────────────┐
│  analysis/filter.py              │────▶│  CoinGecko API       │
│  TransactionFilter               │     │  ETH/USD price       │
│  ├─ ETH value threshold check    │     │  (cached 60s)        │
│  ├─ ERC-20 Transfer log parsing  │     └──────────────────────┘
│  └─ Returns WhaleTransaction     │
└──────────────────┬───────────────┘
                   │ whale detected (≥ MIN_WHALE_USD)
                   ▼
┌──────────────────────────────────┐
│  analysis/labeler.py             │
│  ├─ Address → label lookup       │
│  │  (Binance, Coinbase, Uniswap…)│
│  └─ Direction classification     │
│     (from_exchange/to_exchange/  │
│      wallet_to_wallet)           │
└────────────┬─────────────────────┘
             │
     ┌───────┴────────┐
     │                │
     ▼                ▼
┌─────────┐    ┌────────────────────────┐
│ SQLite  │    │ alerts/telegram_alert  │
│ via     │    │ TelegramAlert          │
│SQLAlch- │    │ ├─ MarkdownV2 format   │
│emy 2.0  │    │ └─ python-telegram-bot │
└─────────┘    └────────────────────────┘
     │                │
     └───────┬─────────┘
             │
             ▼
┌─────────────────────────────┐
│  api/main.py  (FastAPI)     │
│  GET /health                │
│  GET /stats                 │
│  GET /transactions          │
└─────────────────────────────┘
```

---

## Key Components

### 1. Ethereum Feed (`feeds/ethereum_feed.py`)

The entry point for all blockchain data. Opens a persistent WebSocket connection to an Alchemy node and subscribes to `newPendingTransactions`.

**Connection lifecycle:**
```
start()
  └─ while True:
       try:
         _connect_and_subscribe()  ← blocks until disconnect
         backoff = 1               ← reset on clean exit
       except:
         sleep(backoff)            ← 1s, 2s, 4s … up to 60s
         backoff = min(backoff*2, 60)
```

**Per-transaction flow:**
```
WebSocket message arrives (tx_hash)
  └─ asyncio.ensure_future(_process_tx_hash(tx_hash))
       ├─ w3.eth.get_transaction(tx_hash)     ← HTTP fetch
       ├─ w3.eth.get_transaction_receipt(tx_hash)
       ├─ tx_filter.analyze_transaction(tx, receipt)
       └─ if whale: _on_whale_detected(whale_tx)
              ├─ persist to DB (idempotent)
              └─ send Telegram alert
```

**Design choices:**
- `asyncio.ensure_future` fires each tx as a separate coroutine — non-blocking
- Separate WebSocket (for subscriptions) vs HTTP (for tx fetching): Alchemy requires this split
- `ping_interval=20, ping_timeout=30`: keeps the WebSocket alive under load

---

### 2. Transaction Filter (`analysis/filter.py`)

Decides whether a transaction is whale-sized and extracts structured data from raw web3 dicts.

**Detection pipeline:**

```
analyze_transaction(tx, receipt)
  │
  ├─ Step 1: Native ETH check
  │    value_wei = tx["value"]
  │    value_usd = (value_wei / 1e18) * eth_price
  │    if value_usd >= MIN_WHALE_USD → return WhaleTransaction(token="ETH")
  │
  └─ Step 2: ERC-20 Transfer log scan
       for log in receipt["logs"]:
         topic[0] == keccak256("Transfer(address,address,uint256)")?
         contract_address in KNOWN_TOKENS?  (USDT, USDC, WETH)
         decode: from, to, amount (using token decimals)
         if usd_value >= MIN_WHALE_USD → return WhaleTransaction(token=symbol)
```

**ETH price caching:**
```python
# Avoids hammering CoinGecko on every transaction
if cache_age < 60s:
    return cached_price
else:
    fetch from CoinGecko → update cache
```

**WhaleTransaction dataclass:**
```python
@dataclass
class WhaleTransaction:
    hash: str
    from_address: str
    to_address: str
    value_eth: Decimal     # token units (post-decimals division)
    value_usd: float       # USD at time of detection
    token_symbol: str      # "ETH", "USDT", "USDC", "WETH"
    block_number: int
    timestamp: datetime    # UTC
    from_label: str        # e.g. "Binance Hot Wallet"
    to_label: str
    direction: str         # from_exchange / to_exchange / wallet_to_wallet
    gas_used: int
```

---

### 3. Address Labeler (`analysis/labeler.py`)

Maps Ethereum addresses to human-readable labels and classifies transaction direction.

**Registry:**
```python
KNOWN_WALLETS = {
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance Hot Wallet",
    "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3": "Coinbase",
    "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D": "Uniswap V2 Router",
    # ... 17 entries total
}
```

**Direction classification:**
```
from_label ∈ EXCHANGE_LABELS AND to_label ∉ EXCHANGE_LABELS
  → "from_exchange"  (possible withdrawal / accumulation signal)

to_label ∈ EXCHANGE_LABELS AND from_label ∉ EXCHANGE_LABELS
  → "to_exchange"    (possible sell signal)

neither ∈ EXCHANGE_LABELS
  → "wallet_to_wallet"
```

**Lookup is O(1)** — normalized lowercase dict at import time.

---

### 4. Telegram Alert (`alerts/telegram_alert.py`)

Formats and sends a MarkdownV2 message to the configured Telegram chat.

**Message format:**
```
🐋 *WHALE ALERT*

💰 $1,200,000 USDC
📤 From: Binance Hot Wallet
📥 To: Unknown Wallet (0x9f3a...b12c)
⛽ Gas: 65,000 | Block: #19,450,123
🔗 https://etherscan.io/tx/0xabc...def
💡 Possible withdrawal/accumulation
```

**Safety:**
- Silently skips if `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` not set
- All MarkdownV2 special characters are escaped before sending
- Exceptions logged, never crash the main loop

---

### 5. Database Models (`models/database.py`)

SQLAlchemy 2.0 ORM with two tables.

**transactions table:**
```sql
CREATE TABLE transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash     VARCHAR(66) UNIQUE NOT NULL,   -- prevents duplicates
    from_address VARCHAR(42) NOT NULL,
    from_label  VARCHAR(100) NOT NULL,
    to_address  VARCHAR(42),
    to_label    VARCHAR(100) NOT NULL,
    value_eth   NUMERIC(18,8) NOT NULL,
    value_usd   NUMERIC(18,2) NOT NULL,
    token_symbol VARCHAR(20) NOT NULL,
    block_number BIGINT,
    direction   VARCHAR(30) NOT NULL,
    created_at  DATETIME NOT NULL
);
```

**known_wallets table:**
```sql
CREATE TABLE known_wallets (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    address  VARCHAR(42) UNIQUE NOT NULL,
    label    VARCHAR(100) NOT NULL,
    category VARCHAR(30) NOT NULL,
    created_at DATETIME NOT NULL
);
```

**Idempotent writes:**
```python
existing = session.query(Transaction).filter_by(tx_hash=hash).first()
if existing is None:
    session.add(record)
    session.commit()
# Already exists? Skip silently.
```

---

### 6. FastAPI REST API (`api/main.py`)

Three endpoints for monitoring and querying data.

| Endpoint | Response |
|----------|----------|
| `GET /health` | `{status, connected, uptime_seconds}` |
| `GET /stats` | Today's totals: alerts, volume, top tokens, last alert |
| `GET /transactions` | Paginated list with optional `?token=USDC` filter |

**`connected` flag:** Reads `EthereumFeed.connected` property — `true` only when WebSocket is live.

---

## Concurrency Model

```
asyncio event loop
├─ uvicorn.Server.serve()       ← FastAPI HTTP server
└─ EthereumFeed.start()         ← WebSocket + tx processing
     └─ asyncio.ensure_future() ← One coroutine per tx hash (fire-and-forget)
```

**Why `ensure_future` instead of `await`?**
- `await _process_tx_hash()` would block the WebSocket reader until the tx fetch completes
- Ethereum can produce hundreds of tx hashes per second
- `ensure_future` fires each independently — WebSocket reader stays responsive

**SQLAlchemy sessions:**
- Created and closed per-write (`SessionLocal()` → `close()`)
- `check_same_thread=False` for SQLite (required for asyncio)
- No async ORM needed: DB writes are fast and infrequent vs tx volume

---

## Data Flow — Full Scenario

```
01. Alchemy WebSocket pushes tx hash "0xabc..."
02. EthereumFeed receives hash → ensure_future(_process_tx_hash)
03. w3.eth.get_transaction("0xabc...") → {value: 167e18, from: "0x28C6...", to: "0x9f3a..."}
04. w3.eth.get_transaction_receipt("0xabc...") → {gasUsed: 21000, logs: [...]}
05. TransactionFilter.analyze_transaction(tx, receipt)
    a. get_eth_price() → $3,000 (from cache)
    b. 167 ETH × $3,000 = $501,000 ≥ MIN_WHALE_USD ($500,000) ✓
    c. Returns WhaleTransaction(hash="0xabc...", value_usd=501000, token="ETH")
06. Labeler: get_label("0x28C6...") → "Binance Hot Wallet"
07. Labeler: get_label("0x9f3a...") → "Unknown Wallet"
08. Labeler: get_direction("Binance Hot Wallet", "Unknown Wallet") → "from_exchange"
09. DB: INSERT INTO transactions (...) — skipped if tx_hash already present
10. Telegram: send "🐋 WHALE ALERT\n💰 $501,000 ETH\n📤 From: Binance Hot Wallet..."
11. Log: INFO — "Whale detected: 0xabc... $501000 ETH"
```

---

## Error Handling & Resilience

| Failure | Behaviour |
|---------|-----------|
| WebSocket disconnects | Exponential backoff reconnect (1s → 2s → 4s … → 60s) |
| Tx fetch returns None | Skip silently (pending tx may be dropped) |
| CoinGecko API down | Use cached price; return 0.0 if no cache (tx ignored) |
| DB write fails | `session.rollback()`, log error, continue |
| Telegram fails | Log error, continue (alert dropped, tx still saved) |
| Unknown ERC-20 contract | Skip log (only USDT, USDC, WETH monitored) |

---

## Testing Strategy

### Unit Tests (18 cases)

**test_filter.py (8 tests):**
- ETH above threshold → WhaleTransaction returned
- ETH below threshold → None
- USDC transfer ≥ $500k → detected
- USDC transfer < $500k → ignored
- USD conversion uses current ETH price (mocked)
- ETH price is cached (only 1 HTTP call in 60s)
- Zero ETH, empty logs → ignored
- WETH transfer ≥ $500k → detected

**test_labeler.py (10 tests):**
- Known exchange address → correct label
- Unknown address → "Unknown Wallet"
- Direction from_exchange detected
- Direction to_exchange detected
- Direction wallet_to_wallet detected
- get_category returns "exchange"
- get_category returns "unknown"
- Lowercase address resolved correctly
- Stablecoin category correct
- Bridge category correct

**All tests use mocks** — no real network calls, no Alchemy API key required.

---

## Security Considerations

- `.env` is git-ignored — credentials never committed
- No credentials in source code
- Alchemy key scoped to read-only (no signing)
- Telegram bot only sends, never receives
- API has no authentication (deploy behind firewall or VPN for production)

---

## Deployment

### Docker (recommended)

```bash
git clone https://github.com/Arcan17/crypto-whale-tracker.git
cd crypto-whale-tracker
cp .env.example .env
# Edit .env: set ALCHEMY_WS_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
docker-compose up --build
```

**docker-compose.yml:**
```yaml
services:
  app:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data    # SQLite persistence
    ports:
      - "8081:8080"         # FastAPI health/stats
    restart: unless-stopped
```

### Getting an Alchemy Key (free)

1. Sign up at https://alchemy.com
2. Create a new app → select **Ethereum Mainnet**
3. Copy the **WebSocket URL** → paste into `ALCHEMY_WS_URL` in `.env`

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| WebSocket message rate | ~100–500 pending tx hashes/sec (Ethereum mainnet) |
| Tx fetch latency | ~50–200ms per tx (Alchemy HTTP) |
| Filter + label time | <1ms per tx (in-memory) |
| ETH price refresh | Every 60s (CoinGecko cache) |
| DB write latency | <5ms (SQLite) |
| Telegram delivery | <500ms |

**Memory:** Each pending tx spawns a coroutine (~2KB). At 200 tx/sec with 100ms fetch latency: ~20 concurrent coroutines at any moment. Very low footprint.

---

## Scaling Considerations

| Aspect | Current | At scale |
|--------|---------|----------|
| Database | SQLite | PostgreSQL (swap DATABASE_URL) |
| Alerts | Single chat | Multiple channels / webhooks |
| Tokens | 3 (USDT, USDC, WETH) | Expand KNOWN_TOKENS dict |
| Wallets | 17 known | Enrich from on-chain labeling APIs |
| Networks | Ethereum mainnet | Add Polygon, BSC, Arbitrum feeds |

---

## Future Enhancements

### Short-term
- [ ] Add `USDT` on Tron / BNB chain
- [ ] WebSocket reconnect metric (count, last time)
- [ ] `/alerts` endpoint to query only today's triggered alerts

### Medium-term
- [ ] PostgreSQL support (production-grade persistence)
- [ ] On-chain labeling API integration (Etherscan labels, Nansen)
- [ ] Webhook support (Slack, Discord in addition to Telegram)

### Long-term
- [ ] Multi-chain support (Polygon, Arbitrum, BNB)
- [ ] Machine learning for anomaly detection (unusual wallet patterns)
- [ ] Frontend dashboard (React / Next.js)
