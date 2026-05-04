# SKANDA
## The Ultimate AI Quantitative Trading Engine

An autonomous multi-agent quantitative stack: Python agents use a **ReAct** (reason + act) pattern, stream logs to the UI over WebSockets, and pair with a **React (Vite)** dashboard (pink / purple / black “Carbon Mint” theme).

## System architecture

| Agent | Role |
|--------|------|
| **Data Engineer** | Loads policy from `config/active_policy.json`, fetches **10 USDT symbols in parallel** (mock OHLCV sized to the active timeframe), attaches macro placeholder context. Optional **ccxt** path in execution for live quotes. |
| **Asset Manager** | **Lead–lag** analysis across the universe (BTC, ETH, SOL, XRP, LTC, AVAX, DOGE, DOT, LINK, ADA). Runs each cycle after the data panel is built (`identify_lead_lag`). |
| **Sentiment Analyst** | FinBERT-style sentiment on news payload (GPU when available). |
| **Quant Analyst** | Strategy tools in `strategies/` (EMA, RSI, Bollinger, trendline, MACD) driven by `.skills/quant_analyst/*.md`. |
| **ML Engineer** | CatBoost win-probability / validation (CPU). |
| **Risk Manager** | Deterministic veto + Mem0 memory for repeated vetoes (“strike” alert). |
| **User Proxy** | Alerts and announcements. |
| **Quant Trader** | Paper execution, wallet in `logs/account_balance.json`, fills in `logs/trade_history.json`. |

**Offline backtests:** `agents/backtest_agent.py` + `POST /api/run-backtest` (synthetic history, same strategy modules).

## API (`server.py`, FastAPI)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/status` | Policy + `online`; includes `asset_manager` metadata. |
| GET | `/api/logs` | Trade / risk events (normalized `symbol`, `side`). |
| GET | `/api/analytics` | Metrics from **executed** trades only (vetoes excluded from win rate / Sharpe / curves). |
| GET | `/api/balance` | Paper wallet. |
| POST | `/api/switch-strategy` | Partial policy update. |
| POST | `/api/update-config` | Full policy: `strategy`, `timeframe`, `interval_seconds`, `symbol`. |
| POST | `/api/run-backtest` | Body: `symbol`, `strategy`, `timeframe`, `months`. |
| WS | `/api/stream` | Tails `logs/agent_stream.log` (agent thoughts / actions). |

CORS allows local Vite (`5173`) and regex for other localhost ports.

## Dependencies

### Python

Install from the project root:

```bash
python -m pip install -r requirements.txt
```

**Core libraries** (demo / API): `fastapi`, `uvicorn`, `websockets`, `pandas`, `numpy`, `ccxt`, `pandas-ta`, plus agents stack: `torch`, `transformers`, `catboost`, `mem0ai`, `sentence-transformers`, etc.

**Python version:** use **3.10–3.13** if `pip install -r requirements.txt` fails (e.g. CatBoost / Torch may not support the newest CPython yet). `pydantic` is pulled in by FastAPI.

### Frontend (`frontend/`)

```bash
cd frontend
npm install
```

Notable deps: **React 19**, **Vite**, **Tailwind 4**, **axios**, **lucide-react**, **recharts**.

## Config & logs (demo readiness)

- **`config/active_policy.json`** — strategy, timeframe, `interval_seconds`, `symbol` (must be writable; engine hot-reloads each cycle).
- **`logs/account_balance.json`** — seed **$10,000 USDT** for paper mode (writable).
- **`logs/agent_stream.log`** — created/append-only for the WebSocket console.
- **`logs/trade_history.json`** — created by agents if missing.

`forward_test.py` imports **`AssetManager`** from `agents.asset_manager` and calls **`identify_lead_lag`** after each `fetch_market_data()`.

## Launch sequence (three terminals)

From **`c:\Users\kusha\Desktop\ai-trader`** (adjust path on your machine).

**1 — Trading engine (live / forward-test loop)**

```bash
python forward_test.py
```

**2 — FastAPI bridge**

```bash
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

**3 — React dashboard**

```bash
cd frontend
npm run dev
```

Open the URL Vite prints (typically **http://localhost:5173**). The UI expects the API at **http://localhost:8000**.

## Validating the Asset Manager

After starting the engine (and optionally the WebSocket UI):

1. **Console:** Each cycle prints **`[AssetManager] Thinking:`** followed by text like *Identifying lead–lag structure across 10 symbols*.
2. **`logs/agent_stream.log`:** JSON lines with `"agent": "AssetManager"` and the same message; the dashboard **Agent Console** shows **`[AssetManager]`**.
3. **Payload:** The returned structure includes **`symbols_used`** (up to 10) and **`top_pairs`** when overlap is sufficient; if data is thin, you may see a **`note`** instead.

---

*This README reflects the architecture as of the multi-coin Asset Manager, analytics filters, backtest endpoint, and themed dashboard work.*
