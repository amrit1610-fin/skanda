from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict, field_validator
from contextlib import asynccontextmanager
import json
import os
os.environ['OMP_NUM_THREADS'] = '2'
import asyncio
import copy
import numpy as np
import pandas as pd
import uvicorn
from typing import List, Dict
from collections import defaultdict
from datetime import datetime, timezone

from agents.backtest_agent import run_backtest
from agents.asset_manager import UNIVERSE as MULTI_COIN_UNIVERSE
from agents.data_engineer import DataEngineer
from agents.macro_economist import MacroEconomist
from utils.account_manager import AccountManager

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
        MACRO_ECONOMIST.train_model(train_df)
    except Exception as e:
        print(f"MacroEconomist training on live warm-up failed: {e}")
        try:
            MACRO_ECONOMIST.train_model(_bootstrap_macro_training_df(700))
        except Exception as e2:
            print(f"MacroEconomist synthetic bootstrap failed: {e2}")

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
            pass


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
    0: "Multi-TF Trendline Break",
    1: "8/30 EMA Momentum",
    2: "9/15 EMA Scalping",
}


def _bootstrap_macro_training_df(rows: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    price = 30000.0
    closes = []
    for i in range(rows):
        # Piecewise synthetic behavior to ensure all 3 clusters are represented.
        if i < rows // 3:
            shock = rng.normal(0.0, 0.0025)
        elif i < (2 * rows) // 3:
            shock = 0.0015 + rng.normal(0.0, 0.003)
        else:
            shock = rng.normal(0.0, 0.012)
        price = max(100.0, price * (1.0 + shock))
        closes.append(price)
    return pd.DataFrame({"close": closes})


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
                    price_df = pd.DataFrame({"close": prices[-240:]}) if prices else _bootstrap_macro_training_df(240)
                else:
                    price_df = _bootstrap_macro_training_df(240)
            else:
                price_df = _bootstrap_macro_training_df(240)

        detection = MACRO_ECONOMIST.detect_current_regime(price_df)
    except Exception:
        detection = {
            "regime_id": 0,
            "regime_name": "Sideways / Mean Reversion",
            "confidence_pct": 0.0,
        }

    regime_id = int(detection.get("regime_id", 0))
    return {
        "regime_id": regime_id,
        "regime_name": detection.get("regime_name", "Sideways / Mean Reversion"),
        "confidence_pct": float(round(float(detection.get("confidence_pct", 0.0)), 2)),
        "active_strategy": REGIME_STRATEGY_MAP.get(regime_id, "8/30 EMA Momentum"),
    }


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


# --- Pydantic Schemas ---
class StrategySwitchRequest(BaseModel):
    strategy: str
    interval_seconds: int = Field(default=3600, ge=60)

VALID_TIMEFRAMES = frozenset({"5m", "15m", "1h", "4h"})


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
        print(f"File tailing error: {e}")

# --- REST Endpoints ---

@app.get("/api/status")
def get_status():
    """Returns active policy config. Always returns 200 so the frontend can detect the backend is alive."""
    config_path = os.path.join(BASE_DIR, 'config', 'active_policy.json')
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
            data["online"] = True
            # Ensure timeframe always present
            if "timeframe" not in data:
                data["timeframe"] = "5m"
            if "alpha_half_life_seconds" not in data:
                data["alpha_half_life_seconds"] = 300
            if "alpha_decay_veto_threshold" not in data:
                data["alpha_decay_veto_threshold"] = 0.5
            latest_decay = _latest_signal_decay_from_logs()
            if latest_decay is not None:
                data["latest_signal_decay"] = round(latest_decay, 6)
            data["asset_manager"] = {
                "agent": "AssetManager",
                "role": "multi_coin_lead_lag",
            }
            return data
    except Exception:
        return {
            "strategy": "ema",
            "timeframe": "5m",
            "interval_seconds": 3600,
            "symbol": "BTCUSDT",
            "alpha_half_life_seconds": 300,
            "alpha_decay_veto_threshold": 0.5,
            "online": True,
            "asset_manager": {
                "agent": "AssetManager",
                "role": "multi_coin_lead_lag",
            },
        }


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

@app.post("/api/switch-strategy")
def switch_strategy(request: StrategySwitchRequest):
    """Updates the active_policy.json file which the forward test monitors."""
    config_path = os.path.join(BASE_DIR, 'config', 'active_policy.json')
    try:
        # Preserve existing fields (e.g., timeframe, symbol)
        existing = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                existing = json.load(f)
        existing.update({
            "strategy":         request.strategy,
            "interval_seconds": request.interval_seconds,
        })
        with open(config_path, 'w') as f:
            json.dump(existing, f, indent=4)
        return {"status": "success", "message": "Policy updated successfully", "data": existing}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/update-config")
def update_config(request: UpdateConfigRequest):
    """Full config update — persists strategy, timeframe, interval_seconds, and symbol."""
    config_path = os.path.join(BASE_DIR, 'config', 'active_policy.json')
    try:
        tf = request.timeframe if request.timeframe in VALID_TIMEFRAMES else "5m"
        sym = request.symbol
        if sym not in MULTI_COIN_UNIVERSE:
            sym = "BTCUSDT"
        existing = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing.update({
            "strategy":         request.strategy.strip().lower(),
            "timeframe":        tf,
            "interval_seconds": int(request.interval_seconds),
            "symbol":           sym,
        })
        if "alpha_half_life_seconds" not in existing:
            existing["alpha_half_life_seconds"] = 300
        if "alpha_decay_veto_threshold" not in existing:
            existing["alpha_decay_veto_threshold"] = 0.5
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(existing, f, indent=4)
        return {"status": "success", "message": "Config updated", "data": existing}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/run-backtest")
def api_run_backtest(request: BacktestRequest):
    """Run offline multi-month backtest for a single symbol + strategy (synthetic OHLCV)."""
    sym = request.symbol if request.symbol in MULTI_COIN_UNIVERSE else "BTCUSDT"
    strat = (request.strategy or "ema").strip().lower()
    tf = request.timeframe if request.timeframe in VALID_TIMEFRAMES else "1h"
    result = run_backtest(sym, strat, timeframe=tf, months=int(request.months))
    return result

@app.post("/api/toggle-mode")
def toggle_mode(request: ToggleModeRequest):
    """Switch system between Paper (Testnet) and Real (Mainnet) trading modes."""
    global SYSTEM_CONFIG
    SYSTEM_CONFIG["is_paper_trading"] = request.is_paper
    ACCOUNT_MANAGER.initialize_exchange(request.is_paper)
    return {"status": "success", "mode": "paper" if request.is_paper else "real"}


def _normalize_trade_log_entry(log: dict) -> dict:
    """Ensure symbol + side exist for dashboard / exports (non-destructive for unknown keys)."""
    e = log
    if not e.get("symbol"):
        e["symbol"] = "BTCUSDT"
    st = str(e.get("signal_type", "HOLD")).upper()
    e["signal_type"] = st
    if not e.get("side"):
        if st == "BUY":
            e["side"] = "LONG"
        elif st == "SELL":
            e["side"] = "SHORT"
        else:
            e["side"] = "FLAT"
    e["strategy_used"] = e.get("strategy_used", "unknown")
    e["win_probability"] = e.get("win_probability", 0.0)
    if e.get("decay_factor") is not None:
        try:
            e["decay_factor"] = float(e["decay_factor"])
        except (TypeError, ValueError):
            e["decay_factor"] = None
    if e.get("pair_z_score") is not None:
        try:
            e["pair_z_score"] = float(e["pair_z_score"])
        except (TypeError, ValueError):
            e["pair_z_score"] = None
    if e.get("pair_p_value") is not None:
        try:
            e["pair_p_value"] = float(e["pair_p_value"])
        except (TypeError, ValueError):
            pass
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
    """Compute full quantitative metrics for a set of trades."""
    if not trades:
        return None

    pnl_list = [t.get("pnl", 0.0) for t in trades]
    prices   = [t.get("entry_price") for t in trades if t.get("entry_price") is not None]

    # Win / Loss split
    wins   = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]

    win_rate     = (len(wins) / len(trades) * 100.0) if trades else 0.0
    avg_win      = float(np.mean(wins))  if wins   else 0.0
    avg_loss     = float(np.mean(losses)) if losses else 0.0

    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    profit_factor = (
        "Infinity" if gross_loss == 0 and gross_profit > 0
        else 0.0 if gross_loss == 0
        else round(gross_profit / gross_loss, 2)
    )

    price_volatility = float(np.std(prices)) if len(prices) > 1 else 0.0

    # Equity curve + Max Drawdown + daily PnL
    equity      = 1.0
    peak_equity = 1.0
    max_drawdown = 0.0
    daily_pnl: Dict[str, float] = {}
    equity_curve = []

    for t in trades:
        ts    = t.get("timestamp", "")
        pnl   = t.get("pnl", 0.0)

        if ts:
            date_str = ts.split("T")[0]
            daily_pnl[date_str] = daily_pnl.get(date_str, 0.0) + pnl

        equity *= (1 + pnl)
        if equity > peak_equity:
            peak_equity = equity
        drawdown = (peak_equity - equity) / peak_equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        equity_curve.append({
            "timestamp":   ts,
            "equity":      round(equity, 6),
            "entry_price": t.get("entry_price"),
            "exit_price":  t.get("exit_price"),
            "pnl":         pnl,
        })

    # Sharpe Ratio (annualised approximation using daily returns)
    daily_returns = list(daily_pnl.values())
    if len(daily_returns) > 1:
        mean_r = np.mean(daily_returns)
        std_r  = np.std(daily_returns)
        sharpe = float(mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_trades":          len(trades),
        "win_rate_percent":      round(win_rate, 2),
        "sharpe_ratio":          round(sharpe, 2),
        "max_drawdown_percent":  round(max_drawdown * 100.0, 2),
        "profit_factor":         profit_factor,
        "avg_win_percent":       round(avg_win * 100.0, 2),
        "avg_loss_percent":      round(avg_loss * 100.0, 2),
        "price_volatility":      round(price_volatility, 2),
        "daily_pnl":             daily_pnl,      # { "YYYY-MM-DD": float }  → Calendar
        "equity_curve":          equity_curve,   # [ {timestamp, equity, entry_price, exit_price, pnl} ] → Chart
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
    STRATEGIES = ["ema", "rsi", "bollinger", "trendline", "macd", "pairs_trading", "mean_reversion"]

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
        "global_metrics": {
            "total_trades":          len(executed_trades),   # ONLY executed, never vetoed
            "total_vetoes":          veto_count,
            "win_rate_percent":      global_m["win_rate_percent"],
            "sharpe_ratio":          global_m["sharpe_ratio"],
            "max_drawdown_percent":  global_m["max_drawdown_percent"],
            "profit_factor":         global_m["profit_factor"],
            "avg_win_percent":       global_m["avg_win_percent"],
            "avg_loss_percent":      global_m["avg_loss_percent"],
            "daily_pnl":             global_m["daily_pnl"],
            "equity_curve":          global_m["equity_curve"],
        },
        "by_strategy": by_strategy,
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
