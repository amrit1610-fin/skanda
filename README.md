<div align="center">

# ⚡ SKANDA
### Autonomous Multi-Agent Quantitative Crypto Trading Bot

[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![CCXT](https://img.shields.io/badge/CCXT-4.2-FF6B35?style=flat-square)](https://ccxt.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

</div>

---

**Skanda** is a production-grade autonomous trading system that deploys a council of five specialized ReAct AI agents — each with its own reasoning loop, memory, and skill set — to analyze macro market regimes, generate quantitative signals, and execute bracketed limit orders on Binance in real time. Unlike prompt-chaining demos, every agent in Skanda runs deterministic, auditable Python inference: FinBERT for live sentiment scoring, a CatBoost ML classifier for win-probability gating, and a weighted six-timeframe EMA/SMA regime classifier to prevent counter-trend execution.
You can visit here - *https://skanda-livid.vercel.app/*

---

## 🏛️ Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                      React Dashboard (Vite)                      │
│        WebSocket stream · REST analytics · Demo Mode fallback   │
└────────────────────────┬────────────────────────────────────────┘
                         │ ws://  +  http://
┌────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Server (server.py)                    │
│         WebSocket broadcast · REST endpoints · Lifespan          │
└──┬────────────────────────────────────────────────────┬─────────┘
   │ Trading Engine (engine.py)                         │ Analytics
   ▼                                                    ▼
┌─────────────────────────────────────┐     /api/logs · /api/analytics
│          Agent Council              │     /api/balance · /api/status
│                                     │
│  1. DataEngineer  ──→  CCXT REST +  │
│                        WS Klines    │
│  2. MacroEconomist ──→ MTF Radar    │
│                        (6 TFs)      │
│  3. SentimentAnalyst → FinBERT NLP  │
│  4. RiskManager   ──→ ML Veto Gate  │
│  5. QuantTrader   ──→ Binance Order │
└─────────────────────────────────────┘
         │ Mainnet          │ Testnet
    (real execution)  (paper trading)
```

---

## ✨ Features

| Feature | Details |
|---|---|
| **Multi-Agent ReAct Council** | 5 specialized agents (DataEngineer, MacroEconomist, SentimentAnalyst, RiskManager, QuantTrader) each with their own reasoning loop, skill prompt, and Mem0 vector memory |
| **MTF Regime Radar** | Classifies market regime across 6 timeframes (1m → 1d) using EMA20/EMA50/SMA200 alignment. Generates a weighted OVERALL_MACRO_SCORE ∈ [−1.0, +1.0] that vetoes counter-trend trades |
| **FinBERT Sentiment Analysis** | Local ProsusAI/FinBERT inference (no external API calls) scoring each trading cycle. Feeds the ML gate as a real-time signal modifier |
| **CatBoost ML Win-Probability Gate** | Trained on historical BTCUSDT feature set. Blocks execution unless predicted win probability ≥ 55% |
| **Alpha Decay Veto** | Exponential freshness scoring (e^{-λt}) on each signal. Stale signals are automatically rejected before risk calculations |
| **Dual-Exchange Routing** | Hot-swap between Binance Mainnet (live) and Binance Testnet (paper) via a single config flag — no code changes required |
| **WebSocket Telemetry** | Real-time agent thought-stream broadcast from a tail-log async loop. Every agent `think()` and `act()` call appears live in the dashboard console |
| **Vercel Demo Mode** | Frontend detects backend unavailability within 3.5s and seamlessly falls back to animated mock data — including a drifting MTF Regime Radar |
| **Standalone CLI Backtester** | `run_backtest.py` fetches real Binance OHLCV directly into RAM via CCXT pagination and replays it through the identical engine logic |

---

## 🧱 Tech Stack

### Backend (Python)
| Layer | Technology |
|---|---|
| API Server | FastAPI 0.110 + Uvicorn (ASGI) |
| WebSocket | FastAPI WebSocket + `websockets` 12 |
| Exchange Broker | CCXT 4.2 (Binance REST + WebSocket klines) |
| ML / NLP | CatBoost, PyTorch 2.9 (CPU), HuggingFace Transformers 5.7 |
| NLP Model | ProsusAI/FinBERT (local inference) |
| Agent Memory | Mem0ai + ChromaDB (local vector store) |
| Quant Math | Pandas 2.1, NumPy 1.26, SciPy, statsmodels |
| Technical Analysis | pandas-ta |
| Secrets | python-dotenv |

### Frontend (React / Vite)
| Layer | Technology |
|---|---|
| Framework | React 18 + Vite |
| Styling | Vanilla CSS (glassmorphism dark theme) |
| Charts | Recharts |
| Icons | Lucide React |
| HTTP | Axios |
| Real-time | Native browser WebSocket API |
| Deployment | Vercel (with automatic Demo Mode fallback) |

---

## 🚀 Local Setup

### Prerequisites
- Python 3.11+ (tested on 3.14)
- Node.js 18+
- A Binance Testnet account ([register here](https://testnet.binance.vision/))

### 1 · Clone & Python Environment

```bash
git clone https://github.com/YOUR_USERNAME/skanda.git
cd skanda

# Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install all Python dependencies
pip install -r requirements.txt
```

> **Note on PyTorch:** The `requirements.txt` installs the CPU-only build of PyTorch.  
> For CUDA (GPU inference), replace the torch line with:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cu121
> ```

### 2 · Configure Environment Variables

Create a `.env` file in the project root:

```bash
# .env — DO NOT COMMIT THIS FILE
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret_here

# Optional: Add real mainnet keys ONLY for live trading
# BINANCE_API_KEY=your_mainnet_key
# BINANCE_API_SECRET=your_mainnet_secret
```

> ⚠️ **Security:** `.env` is listed in `.gitignore` and will never be committed.  
> Real mainnet keys are never required to run the system in paper-trading mode.

### 3 · Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 4 · Start the System (3-Terminal Boot Sequence)

Open **three separate terminals** from the project root:

**Terminal 1 — FastAPI Backend:**
```bash
cd skanda
venv\Scripts\activate    # or source venv/bin/activate
python server.py
# Server will be live at: http://localhost:8000
```

**Terminal 2 — React Frontend:**
```bash
cd skanda/frontend
npm run dev
# Dashboard will be live at: http://localhost:5173
```

**Terminal 3 — Trading Engine (optional for paper trading):**
```bash
cd skanda
venv\Scripts\activate
python main.py
# Boots the autonomous agent council and begins live paper trading
```

### 5 · Optional: Run a Backtest from the CLI

Edit the parameters at the bottom of `run_backtest.py`, then:

```bash
python run_backtest.py
# Fetches real Binance OHLCV directly into RAM — no CSV files needed
```

---

## 🌐 Vercel Demo Mode

The React frontend is **fully deployable to Vercel** as a static site.

When the frontend cannot reach the backend WebSocket (i.e., when deployed without a running server), it automatically activates **Demo Mode** within 3.5 seconds:

- All state is seeded from `src/utils/mockData.js` with realistic randomised values
- The MTF Regime Radar updates every 4 seconds with drifting market data
- A subtle amber badge — **"UI Demo Mode — Backend Engine Offline"** — appears in the top-right corner
- No errors, no blank screens, no broken charts

**Deploy to Vercel:**
```bash
cd frontend
npx vercel --prod
```

---

## 📁 Project Structure

```
skanda/
├── server.py              # FastAPI ASGI server — WebSocket + REST API
├── engine.py              # Universal trading loop (live & backtest)
├── main.py                # Live bot entry point (autonomous loop)
├── run_backtest.py        # Standalone CLI backtester
├── requirements.txt       # Pinned Python dependencies
│
├── agents/                # ReAct AI Agent Council
│   ├── base_agent.py      # ReActAgent base class (think/act/log)
│   ├── data_engineer.py   # CCXT REST + WebSocket hybrid data faucet
│   ├── macro_economist.py # GMM regime + MTF Regime Radar (6 timeframes)
│   ├── sentiment_analyst.py # FinBERT local NLP inference
│   ├── risk_manager.py    # 4-gate veto logic + Mem0 strike detection
│   ├── quant_trader.py    # Binance order execution (mainnet/testnet)
│   ├── backtest_agent.py  # Backtesting simulation engine
│   ├── asset_manager.py   # Multi-coin universe + cointegration scanner
│   ├── quant_analyst.py   # Signal generation + indicator calculations
│   └── ensemble_manager.py # Multi-strategy signal aggregator
│
├── core_logic/            # Shared computation (used by all drivers)
│   ├── strategies.py      # EMA 8/30, EMA 9/15, Trendline Break signals
│   └── ml_inference.py    # CatBoost win-probability scoring
│
├── ml_pipeline/           # Model training scripts (offline, one-time)
│   ├── 1_build_dataset.py # Feature engineering from OHLCV
│   ├── 2_train_model.py   # XGBoost baseline trainer
│   └── train_catboost.py  # CatBoost production trainer
│
├── config/
│   └── active_policy.json # Hot-reloadable strategy/timeframe/symbol config
│
├── utils/                 # Shared utilities
│   └── alpha_decay.py     # Exponential signal freshness scoring
│
├── docs/
│   └── SKANDA_ARCHITECTURE.md  # Deep-dive technical documentation
│
└── frontend/              # React + Vite dashboard
    └── src/
        ├── App.jsx        # Root — WebSocket + Demo Mode fallback
        ├── utils/mockData.js    # Realistic demo data generator
        ├── components/
        │   ├── DemoModeBadge.jsx # Amber "Demo Mode" indicator
        │   ├── RegimeMatrix.jsx  # MTF Regime Radar visualizer
        │   ├── AgentConsole.jsx  # Live agent thought-stream overlay
        │   └── ...
        └── pages/
            ├── DashboardPage.jsx
            ├── TradeLogPage.jsx
            ├── BacktestPage.jsx
            └── ...
```

---

## ⚖️ Disclaimer

Skanda is a research and portfolio project. It is **not financial advice**. Cryptocurrency trading carries significant risk of financial loss. Always use Testnet (paper trading) mode unless you fully understand the risks of live execution.

---

<div align="center">
Built with ⚡ by Amritanshu &nbsp;|&nbsp; MIT License
</div>
