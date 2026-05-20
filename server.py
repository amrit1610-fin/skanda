from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict, field_validator
from contextlib import asynccontextmanager
import json
import os
os.environ['OMP_NUM_THREADS'] = '2'
import asyncio
import copy
import ccxt
import numpy as np
import pandas as pd
import uvicorn
from typing import List, Dict
from collections import defaultdict
from datetime import datetime, timezone

from agents.asset_manager import UNIVERSE as MULTI_COIN_UNIVERSE
from agents.data_engineer import DataEngineer
from agents.macro_economist import MacroEconomist
from utils.account_manager import AccountManager
from agents.quant_trader import QuantTrader
from agents.risk_manager import RiskManager
from agents.backtest_agent import run_backtest
from engine import run_trading_cycle

ACCOUNT_MANAGER = AccountManager()
SYSTEM_CONFIG = {"is_paper_trading": True}

BASE_DIR = os.path.dirname(__file__)

MACRO_ECONOMIST = None
DATA_ENGINEER: DataEngineer | None = None


def _read_startup_policy() -> dict:
    config_path = os.path.join(BASE_DIR, "config", "active_policy.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "strategy": "ema",
            "timeframe": "5m",
            "interval_seconds": 3600,
            "symbol": "BTCUSDT",
        }

def format_for_delta(symbol: str) -> str:
    """
    Ensures any symbol (e.g., BTCUSDT) is converted 
    to Delta's strict 'BASE/QUOTE:SETTLE' format.
    """
    if not symbol:
        return "BTC/USDT:USDT"
    s = str(symbol).upper().replace("/", "").replace("-", "")
    # If it's already in Delta format (has a colon), return as is
    if ":" in s: 
        return s
    # Standardize Binance-style strings to Delta format
    if s.endswith("USDT"):
        base = s[:-4]
        return f"{base}/USDT:USDT"  
    # Fallback for other formats
    return f"{s}/USDT:USDT"

def _latest_signal_decay_from_logs():
    """Most recent decay_factor from trade_history (risk + execution rows) for dashboard freshness."""
    log_path = os.path.join(BASE_DIR, 'logs', 'trade_history.json')
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return None
        logs = json.loads(content)
        if not logs:
            return None
        for e in sorted(logs, key=lambda x: x.get("timestamp") or "", reverse=True):
            v = e.get("decay_factor")
            if v is not None:
                return float(v)
        return None
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global MACRO_ECONOMIST, DATA_ENGINEER
    ACCOUNT_MANAGER.initialize_exchange(is_paper=True)
    policy = _read_startup_policy()
    sym = str(policy.get("symbol", "BTCUSDT")).strip().upper().replace("/", "").replace("-", "")
    if not sym.endswith("USDT"):
        sym = f"{sym}USDT"
    tf = policy.get("timeframe", "5m")
    if tf not in VALID_TIMEFRAMES:
        tf = "5m"

    DATA_ENGINEER = DataEngineer()
    DATA_ENGINEER.warm_up_historical(sym, tf, limit=500)

    MACRO_ECONOMIST = MacroEconomist()
    try:
        train_df = DATA_ENGINEER.get_latest_market_state()
        if train_df.empty or len(train_df) < 80:
            DATA_ENGINEER.warm_up_historical(sym, tf, limit=800)
            train_df = DATA_ENGINEER.get_latest_market_state()
            
        # PRO FIX: Only train if we actually have real data. 
        if not train_df.empty:
            MACRO_ECONOMIST.train_model(train_df)
        else:
            print("[Warning] Warm-up yielded empty data. MacroEconomist waiting for live ticks.")
            
    except Exception as e:
        print(f"MacroEconomist training on live warm-up failed: {e}")
        # Completely removed the synthetic bootstrap fallback from here!

    _stream_task = asyncio.create_task(DATA_ENGINEER.start_live_stream(sym))
    asyncio.create_task(tail_log_file())
    try:
        yield
    finally:
        if DATA_ENGINEER is not None:
            DATA_ENGINEER.stop_live_stream()
        _stream_task.cancel()
        try:
            await _stream_task
        except asyncio.CancelledError:
            print("[System] Background live stream task terminated gracefully.")

app = FastAPI(title="AI Trader Backend API", lifespan=lifespan)

# CORS: explicit dev origins + regex so alternate ports / IPv6 localhost work with Settings + Backtest UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

REGIME_STRATEGY_MAP = {
    0: "trendline_break",
    1: "ema_8_30",
    2: "ema_9_15",
}


def _compute_economist_data() -> dict:
    try:
        price_df = None
        if DATA_ENGINEER is not None:
            hybrid = DATA_ENGINEER.get_latest_market_state()
            if hybrid is not None and not hybrid.empty and "close" in hybrid.columns:
                price_df = hybrid

        if price_df is None or price_df.empty:
            recent_log_path = os.path.join(BASE_DIR, "logs", "trade_history.json")
            if os.path.exists(recent_log_path):
                with open(recent_log_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    logs = json.loads(content)
                    prices = [x.get("entry_price") for x in logs if x.get("entry_price") is not None]
                    price_df = pd.DataFrame({"close": prices[-240:]}) if prices else pd.DataFrame(columns=["close"])
                else:
                    price_df = pd.DataFrame(columns=["close"])
            else:
                price_df = pd.DataFrame(columns=["close"])

        detection = MACRO_ECONOMIST.detect_current_regime(price_df)
    except Exception:
        detection = {
            "regime_id": 0,
            "regime_name": "Sideways / Mean Reversion",
            "confidence_pct": 0.0,
        }

    regime_id = int(detection.get("regime_id", 0))

    # ── MTF Regime Radar ─────────────────────────────────────────────────────
    # Fetch 6 timeframes in parallel and run the MA-stack classifier.
    # This data is merged into economist_data and broadcast over the WebSocket.
    mtf_result = {"matrix": {}, "overall_macro_score": 0.0, "dominant_regime": "UNKNOWN"}
    if DATA_ENGINEER is not None:
        try:
            policy = DATA_ENGINEER._read_policy()
            sym = policy.get("symbol", "BTCUSDT")
            mtf_dfs = DATA_ENGINEER._fetch_mtf_data(sym)
            mtf_result = MACRO_ECONOMIST.generate_regime_matrix(mtf_dfs)
        except Exception as mtf_err:
            print(f"[MTF] Regime radar broadcast failed: {mtf_err}")

    return {
        "regime_id":           regime_id,
        "regime_name":         detection.get("regime_name", "Sideways / Mean Reversion"),
        "confidence_pct":      float(round(float(detection.get("confidence_pct", 0.0)), 2)),
        "active_strategy":     REGIME_STRATEGY_MAP.get(regime_id, "8/30 EMA Momentum"),
        # MTF fields — consumed by React RegimeMatrix card
        "mtf_matrix":          mtf_result.get("matrix", {}),
        "overall_macro_score": round(float(mtf_result.get("overall_macro_score", 0.0)), 4),
        "dominant_regime":     mtf_result.get("dominant_regime", "SIDEWAYS"),
    }



# --- Pydantic Schemas ---
class StrategySwitchRequest(BaseModel):
    strategy: str
    interval_seconds: int = Field(default=3600, ge=60)

VALID_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


class UpdateConfigRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    strategy: str = Field(default="ema", min_length=1, max_length=64)
    timeframe: str = Field(default="5m", max_length=8)
    interval_seconds: int = Field(default=300, ge=30, le=86400)
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=32)

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        s = (v or "BTCUSDT").strip().upper().replace("/", "").replace("-", "")
        if not s.endswith("USDT"):
            s = f"{s}USDT"
        return s


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(default="BTCUSDT")
    strategy: str = Field(default="ema")
    timeframe: str = Field(default="1h")
    months: int = Field(default=6, ge=1, le=24)

    @field_validator("symbol")
    @classmethod
    def norm_sym(cls, v: str) -> str:
        s = (v or "BTCUSDT").strip().upper().replace("/", "")
        return s if s.endswith("USDT") else f"{s}USDT"


def fetch_memory_ohlcv(symbol: str, timeframe: str, months: int) -> pd.DataFrame:
    """Fetches Binance data directly into memory for the UI backtester."""
    print(f"[*] API fetching {months} months of {timeframe} data for {symbol} via CCXT...")
    exchange = ccxt.binance({'enableRateLimit': True})
    
    days = months * 30
    mapping = {"5m": days * 24 * 12, "15m": days * 24 * 4, "1h": days * 24, "4h": days * 6}
    n_bars = mapping.get(timeframe, days * 24)
    
    all_ohlcv = []
    limit = 1000
    tf_ms_map = {"5m": 300000, "15m": 900000, "1h": 3600000, "4h": 14400000}
    ms_per_candle = tf_ms_map.get(timeframe, 3600000)
    since = exchange.milliseconds() - (n_bars * ms_per_candle)
    ccxt_sym = symbol.replace("USDT", "/USDT") if "USDT" in symbol and "/" not in symbol else symbol
    
    while len(all_ohlcv) < n_bars:
        try:
            bars = exchange.fetch_ohlcv(ccxt_sym, timeframe, since=since, limit=limit)
            if not bars: break
            all_ohlcv.extend(bars)
            since = bars[-1][0] + 1
        except Exception as e:
            print(f"[!] CCXT Fetch Error: {e}")
            break

    df = pd.DataFrame(all_ohlcv[-n_bars:], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    return df

def run_wota_backtest(symbol: str, strategy: str, timeframe: str, months: int):
    """
    Executes the WOTA backtest by streaming CCXT memory data through the agents.
    """
    # 1. Setup Agents
    data_agent = DataEngineer()
    trader_agent = QuantTrader()
    risk_agent = RiskManager()
    
    # 2. Fetch Data Dynamically
    full_df = fetch_memory_ohlcv(symbol, timeframe, months)
    if full_df.empty:
        return {"ok": False, "error": f"Failed to download historical data for {symbol} from Binance."}
        
    # 3. Prime the Time Machine
    data_agent.load_backtest_data({symbol: full_df})
    
    # 4. Prepare Mock Environment
    agents = {
        'data': data_agent,
        'trader': trader_agent,
        'risk': risk_agent,
        'sentiment': None # Bypassed in backtest to save API costs
    }
    
    # PRO FIX: Dynamically patch the policy so it doesn't try to call missing functions
    data_agent._read_policy = lambda: {"strategy": strategy, "timeframe": timeframe, "symbol": symbol}
    
    # 5. Execution Loop
    try:
        from engine import run_trading_cycle
        while True:
            run_trading_cycle(agents, mode="backtest")
    except StopIteration:
        pass # Backtest finished successfully
        
    # 6. Retrieve Results
    logs = trader_agent.get_backtest_logs() if hasattr(trader_agent, 'get_backtest_logs') else []
    return _compute_strategy_metrics(logs)


class ToggleModeRequest(BaseModel):
    is_paper: bool

# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

# Background task to tail the log stream
async def tail_log_file():
    log_file = os.path.join(BASE_DIR, 'logs', 'agent_stream.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            pass

    # The Immortal Retry Loop
    while True:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.5)
                        continue
                    payload = {"type": "stream", "economist_data": _compute_economist_data()}
                    try:
                        payload["event"] = json.loads(line.strip())
                    except json.JSONDecodeError:
                        payload["event"] = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "agent": "system",
                            "type": "info",
                            "message": line.strip(),
                        }
                    await manager.broadcast(json.dumps(payload))
                    
        except Exception as e:
            print(f"[!] File tailing error: {e}. Restarting stream in 5 seconds...")
            await asyncio.sleep(5) # Wait, then loop back to the top and try again

# --- REST Endpoints ---

@app.get("/api/status")
def get_status():
    """
    Returns the active system configuration and real-time alpha metrics.
    Used by the frontend to sync settings and the dashboard 'Freshness' card.
    """
    config_path = os.path.join(BASE_DIR, 'config', 'active_policy.json')
    
    # 1. Load the current policy
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback if config is missing or corrupted
        data = {
            "strategy": "ema_8_30",
            "timeframe": "1h",
            "symbol": "BTCUSDT",
            "interval_seconds": 3600
        }

    # 2. Add System Status Flags
    data["online"] = True # Indicates backend is reachable
    
    # 3. Inject Alpha Freshness 
    # Pull the latest decay factor from the log file to show on the dashboard
    latest_decay = _latest_signal_decay_from_logs()
    data["latest_signal_decay"] = round(latest_decay, 6) if latest_decay is not None else 1.0
    
    # 4. Include Asset Manager Metadata
    data["asset_manager_active"] = True
    
    return data


@app.get("/api/balance")
def get_balance():
    """Returns the current paper trading wallet balance."""
    balance_path = os.path.join(BASE_DIR, 'logs', 'account_balance.json')
    try:
        with open(balance_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Wallet not yet initialised — return seed values
        return {
            "balance_usdt":    10000.00,
            "initial_capital": 10000.00,
            "currency":        "USDT",
            "trade_count":     0
        }
    except json.JSONDecodeError:
        return {"error": "Corrupted balance file"}


@app.post("/api/update-config")
def update_config(request: UpdateConfigRequest):
    """
    Persists strategy, timeframe, interval, and symbol to active_policy.json.
    The engine.py loop monitors this file for hot-reloads.
    """
    config_path = os.path.join(BASE_DIR, 'config', 'active_policy.json')
    try:
        sym = format_for_delta(request.symbol)
        tf = request.timeframe if request.timeframe in VALID_TIMEFRAMES else "5m"
        # Build the payload that both Live and Backtest modes expect
        new_config = {
            "strategy":         request.strategy.strip().lower(),
            "timeframe":        tf,
            "interval_seconds": int(request.interval_seconds),
            "symbol":           sym,
            "alpha_half_life_seconds": 300, # Defaulting for Risk Manager
            "alpha_decay_veto_threshold": 0.5,
            "updated_at":       datetime.now(timezone.utc).isoformat()
        }

        # Save with atomic write to prevent corruption during an engine read
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=4)
            
        print(f"[Config] Policy updated: {new_config['strategy']} on {sym}")
        return {"status": "success", "message": "Config updated", "data": new_config}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/run-backtest")
def api_run_backtest(request: BacktestRequest):
    """
    Routes UI backtest requests to the lightning-fast, vectorized Backtest Agent.
    Bypasses the live execution engine entirely.
    """
    symbol = request.symbol
    strategy = request.strategy
    timeframe = request.timeframe
    months = int(request.months)
    
    try:
        # Call your existing fast backtest agent directly!
        results = run_backtest(
            symbol=symbol,
            strategy=strategy,
            timeframe=timeframe,
            months=months
        )
        return results
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/toggle-mode")
def toggle_mode(request: ToggleModeRequest):
    """Switch system between Paper (Testnet) and Real (Mainnet) trading modes."""
    global SYSTEM_CONFIG
    SYSTEM_CONFIG["is_paper_trading"] = request.is_paper
    ACCOUNT_MANAGER.initialize_exchange(request.is_paper)
    return {"status": "success", "mode": "paper" if request.is_paper else "real"}


def _normalize_trade_log_entry(log: dict) -> dict:
    """
    Standardizes trade log entries for UI consumption.
    Updated to prioritize WOTA execution prices and alpha decay metrics.
    """
    e = log
    
    # 1. Standardize Symbol (Default to BTCUSDT if missing)
    if not e.get("symbol"):
        e["symbol"] = "BTCUSDT"
        
    # 2. Prioritize Execution Price (The real price with 10bps slippage)
    # If execution_price exists (from WOTA trader), use it as the primary entry_price
    if "execution_price" in e:
        e["entry_price"] = float(e["execution_price"])
    elif e.get("entry_price") is not None:
        e["entry_price"] = float(e["entry_price"])

    # 3. Standardize Signal Type and Side
    st = str(e.get("signal_type", "HOLD")).upper()
    e["signal_type"] = st
    
    if not e.get("side"):
        if st == "BUY":
            e["side"] = "LONG"
        elif st == "SELL":
            e["side"] = "SHORT"
        else:
            e["side"] = "FLAT"

    # 4. Strategy Normalization (Ensure it matches core_logic keys)
    e["strategy_used"] = e.get("strategy_used", "unknown")
    
    # 5. ML & Sentiment Metrics
    e["win_probability"] = float(e.get("win_probability", 0.0))
    e["sentiment_score"] = float(e.get("sentiment_score", 0.0))

    # 6. Alpha Decay Factor (Critical for Dashboard Freshness Card)
    if e.get("decay_factor") is not None:
        try:
            e["decay_factor"] = float(e["decay_factor"])
        except (TypeError, ValueError):
            e["decay_factor"] = None

    # 7. Cointegration/Pair Metrics (Optional)
    for key in ["pair_z_score", "pair_p_value"]:
        if e.get(key) is not None:
            try:
                e[key] = float(e[key])
            except (TypeError, ValueError):
                if key == "pair_z_score": e[key] = None
                
    return e


def _executed_trades_only(logs: list) -> list:
    """Strict executed fills only — vetoes, approvals, and risk noise never affect performance stats."""
    out = []
    for l in logs or []:
        if str(l.get("status", "")).lower() != "executed":
            continue
        out.append(l)
    return out


@app.get("/api/logs")
def get_logs():
    """Fetches the trade history."""
    log_path = os.path.join(BASE_DIR, 'logs', 'trade_history.json')
    try:
        with open(log_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return []
            logs = json.loads(content)
            logs = [_normalize_trade_log_entry(copy.deepcopy(x)) for x in logs]
            logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return logs
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _compute_strategy_metrics(trades: list) -> dict:
    """
    Compute full quantitative metrics for a set of trades.
    Updated to handle 'execution_price' and 'mock_balance_usdt' from WOTA trader.
    """
    if not trades:
        return None

    # Use 'pnl' (fractional) for win/loss stats and 'pnl_usdt' for absolute gains
    pnl_list = [t.get("pnl", 0.0) for t in trades]
    
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]

    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0

    # Equity curve and Max Drawdown calculation
    # We prioritize 'mock_balance_usdt' if available (from backtests/paper)
    equity_curve = []
    max_drawdown = 0.0
    peak_equity = -1.0
    daily_pnl = {}

    for t in trades:
        ts = t.get("timestamp", "")
        # Use the explicit balance if logged, otherwise calculate from PnL
        balance = t.get("balance_after") or t.get("mock_balance_usdt")
        
        if balance:
            current_equity = float(balance)
            if peak_equity == -1.0: peak_equity = current_equity
        else:
            # Fallback for older logs
            pnl = t.get("pnl", 0.0)
            current_equity = (equity_curve[-1]["equity"] * (1 + pnl)) if equity_curve else 10000.0
        
        if ts:
            date_str = ts.split("T")[0]
            daily_pnl[date_str] = daily_pnl.get(date_str, 0.0) + t.get("pnl_usdt", 0.0)

        if current_equity > peak_equity:
            peak_equity = current_equity
        
        drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        equity_curve.append({
            "timestamp": ts,
            "equity_curve": round(current_equity, 2), # Matches frontend key
            "price": t.get("execution_price") or t.get("entry_price"),
            "pnl": t.get("pnl", 0.0)
        })

    # Sharpe Ratio calculation (Annualized)
    daily_returns = list(daily_pnl.values())
    sharpe = 0.0
    if len(daily_returns) > 1:
        std_r = np.std(daily_returns)
        sharpe = float(np.mean(daily_returns) / std_r * np.sqrt(252)) if std_r > 0 else 0.0

    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown * 100.0, 2),
        "avg_win_percent": round(avg_win * 100.0, 2),
        "avg_loss_percent": round(avg_loss * 100.0, 2),
        "daily_pnl": daily_pnl,
        "curve_data": equity_curve  # Primary key for BacktestPage.jsx
    }


@app.get("/api/analytics")
def get_analytics():
    """
    Dual-layer analytics response:
      - global_metrics  : all-time portfolio health across every strategy
      - by_strategy     : per-strategy breakdown for each of the 5 strategies
    """
    log_path = os.path.join(BASE_DIR, 'logs', 'trade_history.json')
    raw_logs: list = []
    try:
        with open(log_path, 'r') as f:
            content = f.read().strip()
            if content:
                raw_logs = json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_logs = []

    veto_count = sum(1 for l in raw_logs if str(l.get("status", "")).lower() == "vetoed")

    # All strategies (always present in response even if empty)
    STRATEGIES = ["ema_8_30", "ema_9_15", "trendline_break"]

    empty_response = {
        "global_metrics": {
            "total_trades": 0,             # 0 executed trades
            "total_vetoes": veto_count,
            "win_rate_percent":     0,
            "sharpe_ratio":         0,
            "max_drawdown_percent": 0,
            "daily_pnl":            {},
            "equity_curve":         [],
        },
        "by_strategy": {s: None for s in STRATEGIES},
    }

    normalized = [_normalize_trade_log_entry(copy.deepcopy(x)) for x in raw_logs]
    executed_trades = _executed_trades_only(normalized)
    if not executed_trades:
        return empty_response

    # Chronological order for drawdown accuracy
    executed_trades.sort(key=lambda x: x.get("timestamp", ""))

    # --- Per-strategy breakdown ---
    strategy_groups: Dict[str, list] = defaultdict(list)
    for t in executed_trades:
        strategy_groups[t.get("strategy_used", "unknown")].append(t)

    by_strategy = {s: None for s in STRATEGIES}
    for strat in STRATEGIES:
        trades = strategy_groups.get(strat, [])
        by_strategy[strat] = _compute_strategy_metrics(trades) if trades else None

    # --- Global metrics (all executed trades pooled) ---
    global_m = _compute_strategy_metrics(executed_trades)

    return {
        "global_metrics": global_m,
        "by_strategy": by_strategy
    }

# --- WebSocket Endpoints ---

@app.websocket("/api/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
