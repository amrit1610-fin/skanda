# Skanda — Master Architecture Document

> **Audience:** Senior Engineers, Quant Leads, and ML Reviewers.  
> **Purpose:** A technical deep-dive into how every layer of the Skanda autonomous trading system is designed, why decisions were made, and how data flows from exchange tick to bracketed limit order.

---

## Table of Contents

1. [System Philosophy](#1-system-philosophy)
2. [High-Level Component Map](#2-high-level-component-map)
3. [The Agent Council — ReAct Architecture](#3-the-agent-council--react-architecture)
4. [Data Pipeline — From Exchange Tick to Trade Signal](#4-data-pipeline--from-exchange-tick-to-trade-signal)
5. [The MTF Regime Radar](#5-the-mtf-regime-radar)
6. [The ML / NLP Intelligence Layer](#6-the-ml--nlp-intelligence-layer)
7. [The Four-Gate Risk Veto System](#7-the-four-gate-risk-veto-system)
8. [Execution Router — Mainnet vs. Testnet Failsafes](#8-execution-router--mainnet-vs-testnet-failsafes)
9. [The WebSocket Telemetry Loop](#9-the-websocket-telemetry-loop)
10. [The Backtest Engine](#10-the-backtest-engine)
11. [Demo Mode Fallback Architecture](#11-demo-mode-fallback-architecture)
12. [Configuration & Hot-Reload](#12-configuration--hot-reload)
13. [Known Limitations & Roadmap](#13-known-limitations--roadmap)

---

## 1. System Philosophy

Skanda is built on two guiding principles:

### 1.1 "Shared Brains, Separate Drivers"

All mathematical and inferential logic — indicator calculations, CatBoost scoring, FinBERT inference, and bracket sizing — lives in shared modules (`core_logic/`, `agents/`). These are **driver-agnostic**: the same `engine.py` trading loop runs under three different "drivers":

| Driver | Entry Point | Mode |
|---|---|---|
| Live Bot | `main.py` | Infinite async loop, real CCXT WebSocket stream |
| API Backtest | `server.py → /api/run-backtest` | Pandas sliding window, `asyncio.to_thread` |
| CLI Backtest | `run_backtest.py` | CCXT-paginated historical data, direct stdout reporting |

This architecture prevents the most common failure mode in trading systems: divergent live/backtest logic that produces misleading backtests.

### 1.2 Deterministic Agents, not Stochastic LLMs

Skanda's agents do **not** call GPT/Claude for trade decisions. Every decision is deterministic, traceable, and latency-bounded:

- Strategy signals come from pure pandas EMA/Donchian math (< 5ms)
- Regime classification comes from MA alignment logic (< 2ms per timeframe)
- Win probability comes from a trained CatBoost tree (< 1ms)
- Sentiment comes from local FinBERT GPU/CPU inference (< 200ms)

The "ReAct" pattern is implemented via `base_agent.py`'s `think()` / `act()` methods, which emit structured JSON logs to a stream file that the WebSocket broadcasts in real time — giving the UI the appearance of live agent reasoning without any LLM latency.

---

## 2. High-Level Component Map

```
┌────────────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ DashboardPage│  │ TradeLogPage │  │ BacktestPage             │ │
│  │ RegimeMatrix │  │ CalendarPage │  │ SettingsPage             │ │
│  └──────┬───────┘  └──────────────┘  └──────────────────────────┘ │
│         │ WebSocket (ws://localhost:8000/api/stream)               │
│         │ REST polling (axios, 5s interval)                        │
└─────────┼──────────────────────────────────────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────────┐
│                    FastAPI ASGI Server (server.py)                  │
│  ┌──────────────────────┐  ┌────────────────────────────────────┐  │
│  │ tail_log_file()       │  │ REST Endpoints                     │  │
│  │ async WebSocket loop  │  │  GET  /api/status                 │  │
│  │ → broadcasts JSON     │  │  GET  /api/analytics              │  │
│  │   with economist_data │  │  GET  /api/logs                   │  │
│  │   + agent events      │  │  GET  /api/balance                │  │
│  └──────────────────────┘  │  POST /api/update-config          │  │
│                             │  POST /api/run-backtest           │  │
│                             └────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Startup Lifespan                                              │   │
│  │  1. DataEngineer.warm_up_historical() — REST seed           │   │
│  │  2. MacroEconomist.train_model() — GMM fit on warm-up data  │   │
│  │  3. DataEngineer.start_live_stream() — Binance WS klines    │   │
│  │  4. tail_log_file() — async log-tail background task        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────┬─────────────────────────────────────────────┘
                       │
         ┌─────────────▼────────────────────────────────────────┐
         │               engine.py — run_trading_cycle()        │
         │                                                        │
         │  Step 1: DataEngineer.fetch_market_data()            │
         │  Step 2: get_signal_for_strategy(df, strategy)       │
         │  Step 3: MacroEconomist.generate_regime_matrix()     │
         │  Step 4: SentimentAnalyst.analyze_sentiment(text)    │
         │  Step 5: SkandaInferenceEngine.calculate_win_prob()  │
         │  Step 6: RiskManager.process_proposal(trade)         │
         │  Step 7: QuantTrader.execute_trade(trade, data)      │
         └────────────────────────────────────────────────────────┘
```

---

## 3. The Agent Council — ReAct Architecture

### 3.1 The Base Class: `agents/base_agent.py`

Every agent inherits from `ReActAgent`, which provides:

```python
class ReActAgent:
    def think(self, thought_text: str):
        """Logs internal reasoning. Emits JSON to agent_stream.log."""
        print(f"[{self.name}] Thinking: {thought_text}")
        self._log_stream("thought", thought_text)

    def act(self, action_name: str, action_data=None) -> dict:
        """Executes an action. Returns a standardized payload dict."""
        self._log_stream("action", f"Executed: {action_name}")
        return {"action": action_name, "data": action_data, "status": "executed"}
```

The `_log_stream()` method appends a JSON line to `logs/agent_stream.log`. The FastAPI `tail_log_file()` coroutine watches this file and broadcasts each new line over the WebSocket — producing the live agent console visible in the dashboard.

**Skill loading:** Each agent is instantiated with a path to a Markdown skill file (`.skills/<agent>/system_prompt.md`). The base class reads this file and optionally parses a `Uses Tool:` directive to dynamically import a Python function into `self.active_tool`. This makes each agent's behavior configurable without code changes.

### 3.2 DataEngineer — The Universal Faucet

**File:** `agents/data_engineer.py`

The DataEngineer is the most complex agent. It maintains a **hybrid data buffer**:

```
REST warm-up (CCXT)         WebSocket kline stream (Binance)
       │                              │
       ▼                              ▼
  Historical OHLCV              Partial + Complete
  (seed 500 candles)            candle updates
       │                              │
       └──────────────┬───────────────┘
                      ▼
              _candles: deque[dict]   (max 5000 rows)
              _partial: dict | None  (current open candle)
                      │
                      ▼
              get_latest_market_state()
              → _rows_to_dataframe() → pd.DataFrame
```

**Thread safety:** The candle deque is protected by `threading.RLock()`. The WebSocket runs in an `asyncio` event loop inside a dedicated background thread. CCXT REST calls run in a `ThreadPoolExecutor`.

**MTF parallel fetch:** `_fetch_mtf_data()` launches 6 concurrent REST calls (1m through 1d) using `ThreadPoolExecutor(max_workers=6)`. All 6 complete in ~parallel network time (~300ms) rather than serial ~1.8s.

### 3.3 MacroEconomist — Dual-Mode Regime Intelligence

**File:** `agents/macro_economist.py`

The MacroEconomist operates in two distinct modes:

**Mode 1 — GMM Clustering (dashboard only):**
Trains a `GaussianMixture(n_components=3)` on `[daily_returns, volatility_14, momentum_50]` features. Maps the 3 clusters to: Sideways/Mean-Reversion, Trend Breakout, High Volatility/Chop. Used for the dashboard banner's regime name and confidence percentage.

**Mode 2 — MTF Regime Radar (trading gate):**
See [Section 5](#5-the-mtf-regime-radar) for the full breakdown.

### 3.4 SentimentAnalyst — Local FinBERT NLP

**File:** `agents/sentiment_analyst.py`

```python
# ProsusAI/FinBERT label order: [positive, negative, neutral]
probs = softmax(model(**tokenized_text).logits)
sentiment_score = float(probs[0]) - float(probs[1])  # ∈ [-1.0, +1.0]
```

The model is loaded once at agent initialization to `./models/finbert/` (absolute path pinned to the file's location). On Windows with CPU-only PyTorch, inference takes ~80–150ms per call. The score feeds directly into the CatBoost feature vector.

**Lazy loading pattern:** The model is only downloaded on first use. Subsequent starts check for `tokenizer_config.json` in the cache directory and use `local_files_only=True` to avoid network round-trips.

### 3.5 RiskManager — The Veto Gatekeeper

See [Section 7](#7-the-four-gate-risk-veto-system) for the full veto logic.

**Mem0 integration:** The RiskManager uses `mem0ai` with a local ChromaDB vector store to persist veto memories. After each rejected trade, it stores a natural-language description and runs a semantic similarity search to detect repeat offenders:

```python
self.memory.add("Strategy 'ema_8_30' was vetoed due to ML Win Probability < 55%",
                user_id="risk_manager")
recent = self.memory.search("Strategy 'ema_8_30' was vetoed", limit=5)
veto_count = sum(1 for m in recent if 'ema_8_30' in m.get('memory', ''))
if veto_count >= 3:
    raise_strike_alert()  # Surfaced on the dashboard
```

### 3.6 QuantTrader — The Execution Router

See [Section 8](#8-execution-router--mainnet-vs-testnet-failsafes) for routing logic.

---

## 4. Data Pipeline — From Exchange Tick to Trade Signal

```
Binance WebSocket (btcusdt@kline_5m)
        │
        ▼ [DataEngineer._ws_reader()]
   Parse kline JSON
        │
        ├─── if k["x"] == True (candle closed):
        │        _candles.appendleft(complete_row)
        │        _partial = None
        │
        └─── if k["x"] == False (in-progress):
                 _partial = current_row
        │
        ▼ [engine.py — Step 1]
   DataEngineer.fetch_market_data()
        │
        ├── get_latest_market_state()
        │       → deque → _rows_to_dataframe()
        │       → 250 rows of OHLCV (hybrid REST + WS)
        │
        ├── _fetch_mtf_data(symbol) [ThreadPoolExecutor × 6]
        │       → {"1m": df, "5m": df, ..., "1d": df}
        │
        └── Returns standard_payload dict
        │
        ▼ [engine.py — Step 2]
   get_signal_for_strategy(df, strategy_name)
        │
        ├── EMA 8/30: crossover + slope + ATR filter + volume confirmation
        ├── EMA 9/15: ribbon separation + candlestick snapback
        └── Trendline Break: Donchian channel + EMA200 macro filter
        │
        Returns: "BUY" | "SELL" | "HOLD"
        │
        ▼ Early exit if "HOLD"
        │
        ▼ [engine.py — Steps 3-7]
   MTF Radar → Sentiment → ML Gate → Risk Veto → Execution
```

**Key data contract:** `fetch_market_data()` always returns `{"action": ..., "data": standard_payload, "status": "executed"}`. Engine code extracts via `market_data_response.get("data", {})`. This ensures that if an agent's `act()` returns a malformed response, the engine degrades gracefully to empty dicts rather than crashing.

---

## 5. The MTF Regime Radar

### 5.1 Classification Logic

For each of the 6 timeframes, `_classify_tf_regime(df)` applies this decision tree:

```
Given: price, EMA20, EMA50, SMA200 (last completed candle)

if price > EMA20 > EMA50:
    if EMA50 > SMA200:  → "STRONG_BULLISH"  (score: +1.0)
    else:               → "BULLISH"          (score: +0.6)

elif price < EMA20 < EMA50:
    if EMA50 < SMA200:  → "STRONG_BEARISH"  (score: -1.0)
    else:               → "BEARISH"          (score: -0.6)

else:                   → "SIDEWAYS"         (score:  0.0)
```

**SMA200 handling:** If the DataFrame has fewer than 200 rows, `sma200.iloc[-1]` is `NaN`. The classifier treats this as "SMA200 not yet aligned" and falls back to `BULLISH`/`BEARISH` rather than `STRONG_*` — preventing false strong signals on thin data.

### 5.2 Weighted Aggregation

```python
MTF_WEIGHTS = {"1m": 0.05, "5m": 0.10, "15m": 0.15, "1h": 0.25, "4h": 0.30, "1d": 0.15}

weighted_score = Σ (REGIME_SCORES[regime] × MTF_WEIGHTS[tf])  for all known TFs
overall_macro_score = weighted_score / sum(weights_of_known_TFs)
```

Higher timeframes (4h, 1d) carry 30% and 15% of the total weight respectively. This means a `STRONG_BEARISH` 4h signal contributes −0.30 to the score, while a `BULLISH` 1m signal contributes only +0.05. The system is structurally biased toward respecting higher-timeframe context.

### 5.3 Score Interpretation

| Score Range | Dominant Regime | RiskManager Action |
|---|---|---|
| ≥ +0.50 | STRONG_BULLISH | SELL signals vetoed |
| +0.15 to +0.49 | BULLISH | All signals allowed |
| −0.14 to +0.14 | SIDEWAYS | All signals allowed |
| −0.49 to −0.15 | BEARISH | All signals allowed |
| ≤ −0.50 | STRONG_BEARISH | BUY signals vetoed |

---

## 6. The ML / NLP Intelligence Layer

### 6.1 CatBoost Win-Probability Gate

**Training:** `ml_pipeline/train_catboost.py` trains on `BTCUSD_ml_dataset.csv` with features including:
- EMA crossover state (8/30, 9/15)
- ATR normalized to price
- 14-day rolling volatility
- Volume deviation from SMA(20)
- Sentiment score (FinBERT output)
- Regime cluster ID (GMM output)

**Inference path** (`core_logic/ml_inference.py`):
```python
class SkandaInferenceEngine:
    def calculate_win_probability(self, quant_signal, active_strategy, sentiment_score) -> float:
        # Maps discrete inputs to a feature vector
        # Runs CatBoostClassifier.predict_proba()
        # Returns P(win) × 100 as a percentage
```

The model file is loaded once at module import (when `engine.py` is first imported) rather than per-cycle to avoid multi-second latency on every trade signal.

### 6.2 FinBERT Sentiment Scoring

The `SentimentAnalyst` constructs a dynamic market context string each cycle:
```python
dynamic_text = f"Market action for {symbol} showing patterns consistent with {dominant_regime} conditions."
```

This text is passed through FinBERT. The resulting `sentiment_score ∈ [−1.0, +1.0]` is:
1. Added to `trade_proposal` for the RiskManager
2. Logged to `trade_history.json` for dashboard display
3. Fed into the CatBoost feature vector as a real-time signal modifier

**Why local inference?** External sentiment APIs (NewsAPI, OpenAI) introduce 200ms–2s latency and rate limits. A locally-cached FinBERT model runs in ~100ms on CPU and has zero per-call cost, making it viable for high-frequency cycles.

---

## 7. The Four-Gate Risk Veto System

Every trade proposal passes through four sequential gates. Rejection at any gate stops evaluation immediately.

```
Trade Proposal
      │
      ▼
┌─────────────────────────────────────────┐
│ Gate 1: Alpha Decay                     │
│                                          │
│  score = e^(-λ × Δt)                    │
│  λ = ln(2) / half_life_seconds          │
│  Δt = current_time - signal_timestamp   │
│                                          │
│  if score < alpha_decay_veto_threshold  │
│      → VETO: "Alpha Expired"            │
└───────────────────┬─────────────────────┘
                    │ PASS
                    ▼
┌─────────────────────────────────────────┐
│ Gate 2: Macro Trend Alignment           │
│                                          │
│  if BUY and macro_score < -0.50:        │
│      → VETO: "Fighting Macro Bear"      │
│                                          │
│  if SELL and macro_score > +0.50:       │
│      → VETO: "Fighting Macro Bull"      │
└───────────────────┬─────────────────────┘
                    │ PASS
                    ▼
┌─────────────────────────────────────────┐
│ Gate 3: ML Win Probability              │
│                                          │
│  if win_probability < 55.0:             │
│      → VETO: "ML Win Prob < 55%"        │
│      → Store veto memory in Mem0        │
│                                          │
│  if signal == "HOLD":                   │
│      → VETO: "Signal is HOLD"           │
└───────────────────┬─────────────────────┘
                    │ PASS
                    ▼
┌─────────────────────────────────────────┐
│ Gate 4: Strike Counter (Mem0)           │
│                                          │
│  Semantic search recent veto memories   │
│  if veto_count >= 3 for this strategy:  │
│      → Emit STRIKE_ALERT to dashboard   │
│      (trade still executes if Gates 1-3 │
│       passed — alert is advisory only)  │
└───────────────────┬─────────────────────┘
                    │ APPROVED
                    ▼
             QuantTrader.execute_trade()
```

All decisions — both approved and vetoed — are written to `logs/trade_history.json` with full metadata (signal_type, win_probability, sentiment_score, macro_score, decay_factor, reason). This makes every risk decision fully auditable in the Trade Log page.

---

## 8. Execution Router — Mainnet vs. Testnet Failsafes

### 8.1 Dual Exchange Initialization

`QuantTrader.__init__()` initializes both exchanges at startup:

```python
# Mainnet — real money (keys optional)
self.mainnet_exchange = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY", ""),
    'secret': os.getenv("BINANCE_API_SECRET", ""),
    'options': {'defaultType': 'future'}
})

# Testnet — paper trading (required for demo)
self.testnet_exchange = ccxt.binance({
    'apiKey': os.getenv("BINANCE_TESTNET_API_KEY", ""),
    'secret': os.getenv("BINANCE_TESTNET_API_SECRET", ""),
    'options': {'defaultType': 'future'}
})
self.testnet_exchange.set_sandbox_mode(True)  # Routes to testnet.binance.vision
```

The `set_sandbox_mode(True)` call is the single source of truth for routing. CCXT internally redirects all API calls to `https://testnet.binance.vision` — no manual URL management required.

### 8.2 Order Flow

```python
def execute_trade(self, approved_trade, market_data, mode="live"):
    active_exchange = self.mainnet_exchange if mode == "live" else self.testnet_exchange

    # 1. Fetch live price from the active exchange (mainnet or testnet price)
    ticker = active_exchange.fetch_ticker(ccxt_symbol)
    entry_price = ticker["last"]

    # 2. Fetch real balance from the active account
    balance_data = active_exchange.fetch_balance()
    available_usdt = balance_data['USDT']['free']

    # 3. Risk-based position sizing
    risk_amount = available_usdt * 0.02   # 2% risk per trade
    quantity = risk_amount / entry_price

    # 4. Calculate ATR-based brackets
    brackets = risk_manager.calculate_trade_brackets(side, entry_price, atr=atr)

    # 5. Place bracketed limit order
    order = active_exchange.create_order(
        symbol, 'limit', side, quantity, entry_price,
        params={'stopLossPrice': brackets['stop_loss'],
                'takeProfitPrice': brackets['take_profit']}
    )
```

**Risk-to-reward ratio:** Default SL = 2% of entry, TP = 6% of entry (3:1 RRR). When ATR data is available, brackets are ATR-scaled: `SL = entry - (2 × ATR)`, `TP = entry + (6 × ATR)`.

### 8.3 Minimum Order Guard

```python
if risk_amount < 10.0:
    return {"status": "skipped", "reason": "Trade size below exchange minimum"}
```

Binance enforces a 10 USDT minimum notional. The guard prevents wasted API calls on micro-balance accounts.

---

## 9. The WebSocket Telemetry Loop

### 9.1 Server Side

```python
# server.py — tail_log_file() coroutine
async def tail_log_file():
    with open("logs/agent_stream.log", "r") as f:
        f.seek(0, 2)    # Seek to end of file
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.5)   # Non-blocking yield
                continue
            # Attach economist_data (cached — refreshed every 30s) to every event
            payload = {
                "type": "stream",
                "economist_data": _get_economist_cached(),
                "event": json.loads(line.strip())
            }
            await manager.broadcast(json.dumps(payload))
```

**Caching:** `_compute_economist_data()` makes 6 CCXT API calls for the MTF radar. Without caching, a high-frequency log stream (10+ lines/sec during an active cycle) would generate 60+ Binance API requests per second — well above the rate limit. The 30-second cache refreshes the matrix between cycles without hammering the exchange.

### 9.2 Client Side (React)

```javascript
// App.jsx — WebSocket with 3.5s demo-mode timeout
useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/api/stream');

    // Race: if WS doesn't open within 3500ms → Demo Mode
    const timeoutId = setTimeout(() => {
        if (!didConnect) activateDemoMode();
    }, 3500);

    ws.onopen  = () => { clearTimeout(timeoutId); setIsDemoMode(false); };
    ws.onmessage = (event) => {
        const { economist_data } = JSON.parse(event.data);
        setEconomistData(economist_data);
    };
    ws.onclose = () => {
        if (!didConnect) activateDemoMode();
    };
}, []);
```

---

## 10. The Backtest Engine

### 10.1 Data Architecture — Zero CSV Dependency

```python
# run_backtest.py
while len(all_ohlcv) < n_bars:
    bars = exchange.fetch_ohlcv(ccxt_sym, timeframe, since=since, limit=1000)
    all_ohlcv.extend(bars)
    since = bars[-1][0] + 1   # Advance to next candle timestamp
```

Data lives entirely in process memory. No CSV files are read from or written to disk during a backtest. This eliminates stale-data bugs and makes the backtester portable.

### 10.2 Time Machine Pattern

The `DataEngineer.load_backtest_data()` method stores the full historical DataFrame in memory. `fetch_market_data()` in backtest mode slices a `lookback_window=250` view at `current_step` and advances the pointer:

```python
def fetch_market_data(self):    # backtest mode
    end = self.current_step
    start = max(0, end - self.lookback_window)
    window = self.historical_df.iloc[start:end]
    self.current_step += 1
    if self.current_step > len(self.historical_df):
        raise StopIteration   # Signals the engine loop to stop
    return self.act("fetch_market_data", {"ohlcv_data": window, ...})
```

`StopIteration` propagates out of `engine.py` to the caller's `while True` loop, which catches it and prints the summary — a clean finite-loop termination pattern.

### 10.3 Shared Brain Guarantee

Because `run_backtest.py`, `server.py`, and `main.py` all import and call `engine.run_trading_cycle()`, it is **impossible** for the backtest to use different indicator math than the live bot. Any strategy bug that exists in production will manifest identically in the backtest — there is no hidden "backtest-only" code path.

---

## 11. Demo Mode Fallback Architecture

```
Frontend starts
       │
       ▼
new WebSocket('ws://localhost:8000/api/stream')
       │
       ├── onopen fires within 3500ms?
       │       YES → Normal live mode
       │
       └── NO (timeout or connection refused)
               │
               ▼
          activateDemoMode()
               │
               ├── setStatus(MOCK_STATUS)
               ├── setAnalytics(MOCK_ANALYTICS)
               ├── setLogs(MOCK_LOGS)
               ├── setBalance(MOCK_BALANCE)
               └── setEconomistData(MOCK_ECONOMIST_BASE)
               │
               ▼
          setInterval(tickedEconomistData, 4000ms)
               │
               ▼
          Each tick: drift overall_macro_score by ±0.06
                     randomly mutate 1m or 5m regime state
                     re-render RegimeMatrix (animated)
```

**Mock data realism:** All seed values are randomised once per page-load using `rand(min, max, decimals)`. Balance is always between $10,200 and $11,850 (realistic short-term paper trading P&L). The 30-day equity curve is generated with a geometric random walk seeded from the same initial value, producing natural-looking drawdown and recovery patterns.

---

## 12. Configuration & Hot-Reload

### 12.1 `config/active_policy.json`

```json
{
    "strategy":                  "ema_8_30",
    "timeframe":                 "5m",
    "interval_seconds":          300,
    "symbol":                    "BTCUSDT",
    "alpha_half_life_seconds":   300,
    "alpha_decay_veto_threshold": 0.5
}
```

Every agent reads this file on each cycle via `DataEngineer._read_policy()`. Changes made through the Settings page (`POST /api/update-config`) are written to disk and picked up on the next cycle — **no restart required**.

### 12.2 Hot-Reload Scope

| Parameter | Takes effect | Notes |
|---|---|---|
| `strategy` | Next cycle | Strategy map lookup |
| `timeframe` | Next cycle | CCXT fetch parameter |
| `symbol` | Next cycle | Symbol routing |
| `interval_seconds` | Next `time.sleep()` | Main loop sleep duration |
| `alpha_half_life_seconds` | Next risk gate evaluation | Decay λ recalculated |

---

## 13. Known Limitations & Roadmap

### Current Limitations

| Issue | Impact | Status |
|---|---|---|
| `mode=` parameter removed from engine | Backtest route in server.py crashes with TypeError | Documented in audit; awaiting fix |
| `_compute_economist_data()` per log line | Rate-limit risk at high log frequency | Caching fix designed |
| FinBERT lazy loading not implemented | Startup race condition risk on Windows | Lazy-load pattern documented |
| `quant_trader.py` balance KeyError | Crashes on zero-balance testnet accounts | Audit BUG-04; fix designed |

### Roadmap

- [ ] **Async execution loop** — Replace `main.py`'s blocking `time.sleep()` with `asyncio.sleep()` inside a proper event loop
- [ ] **Multi-asset parallel scanning** — Run the agent council on BTC/ETH/SOL simultaneously with signal priority scoring
- [ ] **Live PnL tracking** — Implement order status polling to close positions and log realized PnL
- [ ] **Discord/Telegram alerts** — Webhook integration for trade executions and strike alerts
- [ ] **Strategy optimization** — Integrate `scripts/optimize_grid.py` into an automated hyperparameter sweep with walk-forward validation
- [ ] **Model retraining pipeline** — Schedule weekly CatBoost retraining on the latest OHLCV + sentiment data

---

*Document maintained by: Kusha | Last updated: May 2026*
