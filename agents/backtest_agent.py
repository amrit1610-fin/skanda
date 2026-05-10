"""
Historical simulation for a single symbol and strategy — upgraded for the Alpha Architecture.

Changes from legacy:
- Feature Engineering: ATR, VWAP, MACD, RSI calculated on every bar.
- Vectorized Confluence Filter: buy/sell gated by VWAP position, MACD crossover, RSI thresholds.
- BTC King Filter: altcoin longs only allowed above the 200-bar SMA (bull regime proxy).
- Event-Driven ATR Bracket Loop: replaces simple log-return accumulation with a
  pessimistic SL/TP state machine (SL hits before TP if both are touched in the same candle).
"""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

from agents.portfolio_manager import PortfolioManager

from utils.math_engine import (
    calculate_atr,
    calculate_vwap,
    calculate_rsi,
    calculate_donchian,
)

# ─── Constants ────────────────────────────────────────────────────────────────
BACKTEST_MONTHS = 6
FEE_PCT = 0.001          # 0.1% round-trip fee per trade
ATR_SL_MULT = 1.5        # Stop Loss = entry ± 1.5 × ATR
ATR_TP_MULT = 3.0        # Take Profit = entry ± 3.0 × ATR
KING_FILTER_SMA = 200    # Bull/bear proxy for altcoins (close > SMA_200 → bull)

STRATEGY_MODULE_MAP: Dict[str, str] = {
    "turtle":    "strategies.turtle",
    "connors":   "strategies.connors",
    "stat_arb":  "strategies.stat_arb",
}

VALID_TIMEFRAMES = {"5m", "15m", "1h", "4h"}
_FREQ_FOR_TF    = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _bars_for_timeframe(tf: str) -> int:
    days = 180
    mapping = {"5m": days * 24 * 12, "15m": days * 24 * 4, "1h": days * 24, "4h": days * 6}
    return mapping.get(tf, days * 24)


def _strategy_fn(strategy: str) -> Callable[[pd.DataFrame], dict]:
    key     = (strategy or "turtle").lower().strip()
    mod_name = STRATEGY_MODULE_MAP.get(key, STRATEGY_MODULE_MAP["turtle"])
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as e:
        import sys
        print(f"[Backtest] ImportError diagnostic: exe={sys.executable}")
        raise e
    return getattr(mod, "analyze")


def _synthetic_ohlcv(symbol: str, n_bars: int, timeframe: str) -> pd.DataFrame:
    """Reproducible GBM-style OHLCV for offline backtests."""
    seed = int(hashlib.sha256(f"{symbol}:{timeframe}".encode()).hexdigest()[:8], 16) % (2**31)
    rng  = np.random.default_rng(seed)

    mu, sigma = 1.2e-5, 0.012
    r     = rng.normal(mu, sigma, n_bars)
    base  = 50.0 + (seed % 10000) / 100.0
    close = base * np.cumprod(1.0 + r)

    noise_hi = np.abs(rng.normal(0, 0.004, n_bars))
    noise_lo = np.abs(rng.normal(0, 0.004, n_bars))

    df = pd.DataFrame({
        "open":   close * (1.0 + rng.uniform(-0.002, 0.002, n_bars)),
        "high":   close * (1.0 + noise_hi),
        "low":    close * (1.0 - noise_lo),
        "close":  close,
        "volume": rng.integers(500, 8000, n_bars).astype(float),
    })
    return df


def _attach_timestamps(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    out   = df.copy()
    start = datetime.now(timezone.utc)                    # Anchor to today, not 2024
    freq  = _FREQ_FOR_TF.get(tf, "1h")
    # Work backwards: last bar = now, first bar = now - n_bars * freq
    n     = len(out)
    idx   = pd.date_range(end=start, periods=n, freq=freq, tz="UTC")
    out["timestamp"] = idx
    return out


# ─── STEP 1: Feature Engineering ─────────────────────────────────────────────

def _engineer_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Compute Universal features.
    Only ATR is globally required for bracket simulation.
    """
    df = df.copy()

    # ATR — kept first; used by bracket simulator downstream
    df["atr"] = calculate_atr(df, period=14)

    return df


# ─── STEP 2: Strategy Dispatcher ─────────────────────────────────────────────

def _generate_signals(df: pd.DataFrame, strategies: list) -> pd.DataFrame:
    if isinstance(strategies, str):
        strategies = [strategies]
    df = df.copy()
    sig_df = pd.DataFrame(index=df.index)
    
    for strategy_name in strategies:
        try:
            module = importlib.import_module(f"strategies.{strategy_name}")
            buy_cond, sell_cond = module.generate_signals(df)
            
            sig_df[strategy_name] = 0
            sig_df.loc[buy_cond, strategy_name] = 1
            sig_df.loc[sell_cond, strategy_name] = -1
        except Exception as e:
            print(f"Failed to generate signals for {strategy_name}: {e}")
            sig_df[strategy_name] = 0

    net_sum = sig_df.sum(axis=1)
    df['signal'] = np.sign(net_sum)
    df['strategy_votes'] = sig_df.to_dict(orient='records')

    return df




# ─── STEP 3: Event-Driven ATR Bracket Loop ────────────────────────────────────

def _run_bracket_simulation(df: pd.DataFrame, pm: PortfolioManager) -> Dict[str, Any]:
    """
    Pessimistic bi-directional SL/TP state machine with dynamic risk profiling.

    Pessimistic rule: if BOTH SL and TP are touched in the same candle, SL hits first.
    """
    trades: list[float] = []
    equity  = 1.0
    equity_curve: list[dict] = []

    in_position   = False
    position_type: str | None = None    # 'long' | 'short'
    entry_price   = 0.0
    sl_price      = 0.0
    tp_price      = 0.0

    # First bar where ATR is valid
    valid_start = df["atr"].first_valid_index()
    valid_start = df.index.get_loc(valid_start) if valid_start is not None else 0

    rows = df.reset_index(drop=True)

    for i, row in rows.iterrows():
        ts  = row["timestamp"]
        hi  = float(row["high"])
        lo  = float(row["low"])
        cls = float(row["close"])
        atr = float(row["atr"]) if not pd.isna(row["atr"]) else None
        sig = int(row["signal"]) if not pd.isna(row["signal"]) else 0

        pnl_pct = None

        # ── Exit logic ────────────────────────────────────────────────────────
        if in_position:
            if position_type == "long":
                # Long wins when high ≥ TP; loses when low ≤ SL
                sl_hit = lo <= sl_price
                tp_hit = hi >= tp_price
                # Pessimistic: SL takes priority if both triggered
                if sl_hit:
                    pnl_pct = (sl_price - entry_price) / entry_price - 0.001
                elif tp_hit:
                    pnl_pct = (tp_price - entry_price) / entry_price - 0.001

            elif position_type == "short":
                # Short wins when low ≤ TP (price fell); loses when high ≥ SL (price rose)
                sl_hit = hi >= sl_price
                tp_hit = lo <= tp_price
                # Pessimistic: SL takes priority if both triggered
                if sl_hit:
                    pnl_pct = (entry_price - sl_price) / entry_price - 0.001
                elif tp_hit:
                    pnl_pct = (entry_price - tp_price) / entry_price - 0.001

            if pnl_pct is not None:
                trades.append(pnl_pct)
                in_position   = False
                position_type = None

        # ── Entry logic (only when flat and ATR is valid) ─────────────────────
        if not in_position and sig != 0 and atr and atr > 0 and i >= valid_start:
            in_position = True
            entry_price = cls
            
            votes = row['strategy_votes']
            sl_dist, tp_dist = pm.calculate_blended_risk(votes, atr)

            if sig == 1:        # LONG
                position_type = "long"
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tp_dist
            else:               # SHORT (sig == -1)
                position_type = "short"
                sl_price = entry_price + sl_dist   # SL is above entry
                tp_price = entry_price - tp_dist   # TP is below entry

        # ── Update equity curve every bar ─────────────────────────────────────
        if pnl_pct is not None:
            equity *= (1.0 + pnl_pct)
        equity_curve.append({
            "timestamp":    ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "equity_curve": round(equity, 6),
        })

    # ── Derived metrics ───────────────────────────────────────────────────────
    wins   = [p for p in trades if p > 0]
    losses = [p for p in trades if p <= 0]

    win_rate      = (len(wins) / len(trades) * 100) if trades else 0.0
    avg_win_pct   = float(np.mean(wins)   * 100) if wins   else 0.0
    avg_loss_pct  = float(np.mean(losses) * 100) if losses else 0.0
    total_ret_pct = (equity - 1.0) * 100

    eq_vals = np.array([e["equity_curve"] for e in equity_curve])
    peak    = np.maximum.accumulate(eq_vals)
    dd      = np.where(peak > 0, (eq_vals - peak) / peak, 0.0)
    max_dd  = float(dd.min() * 100)

    # Sharpe (annualised, per-bar log returns)
    log_rets = np.diff(np.log(eq_vals + 1e-12))
    if log_rets.std() > 1e-12:
        sharpe = float((log_rets.mean() / log_rets.std()) * np.sqrt(8760))
    else:
        sharpe = 0.0

    return {
        "total_return_pct":  round(total_ret_pct, 2),
        "sharpe_ratio":      round(sharpe, 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "win_rate_pct":      round(win_rate, 2),
        "avg_win_pct":       round(avg_win_pct, 4),
        "avg_loss_pct":      round(avg_loss_pct, 4),
        "total_trades":      len(trades),
        "curve_data":        equity_curve,
    }



# ─── Public Entry Point ───────────────────────────────────────────────────────

def run_backtest(
    symbol:    str,
    strategy:  str,
    timeframe: str = "1h",
    months:    int = BACKTEST_MONTHS,
    warmup:    int = 120,
) -> Dict[str, Any]:
    """
    Full Alpha-Upgraded backtest pipeline:
      1. Generate synthetic OHLCV anchored to today.
      2. Engineer ATR / VWAP / MACD / RSI features.
      3. Apply confluence + King Filter to generate signals.
      4. Simulate trades with ATR brackets (pessimistic SL/TP loop).
      5. Return rich metrics dict.
    """
    tf     = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
    n_bars = _bars_for_timeframe(tf)
    if months != BACKTEST_MONTHS:
        n_bars = int(round(n_bars * (months / BACKTEST_MONTHS)))

    # ── Build base OHLCV ──────────────────────────────────────────────────────
    df = _synthetic_ohlcv(symbol, n_bars, tf)
    df = _attach_timestamps(df, tf)

    # ── Feature Engineering ───────────────────────────────────────────────────
    try:
        df = _engineer_features(df, symbol)
    except Exception as exc:
        return {"ok": False, "error": f"Feature engineering error: {exc}", "symbol": symbol, "strategy": strategy}

    # ── Strategy Dispatcher → signal column ──────────────────────────────────
    active_strategies = [s.strip() for s in strategy.lower().split(',')]
    pm = PortfolioManager(active_strategies)
    
    try:
        df = _generate_signals(df, active_strategies)
    except Exception as exc:
        return {"ok": False, "error": f"Signal generation error: {exc}", "symbol": symbol, "strategy": strategy}

    # ── ATR Bracket Simulation (strategy-aware risk profile) ───────────────────────
    try:
        metrics = _run_bracket_simulation(df, pm)
    except Exception as exc:
        return {"ok": False, "error": f"Simulation loop error: {exc}", "symbol": symbol, "strategy": strategy}

    price_curve = [
        {
            'time': row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
            'price': float(row['close'])
        }
        for idx, row in df.iterrows()
    ]

    return {
        "ok":               True,
        "symbol":           symbol,
        "strategy":         strategy.lower().strip(),
        "timeframe":        tf,
        "months":           months,
        "bars":             n_bars,
        "total_return_pct": metrics["total_return_pct"],
        "sharpe_ratio":     metrics["sharpe_ratio"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "win_rate_pct":     metrics["win_rate_pct"],
        "win_rate":         metrics["win_rate_pct"],
        "avg_win_pct":      metrics["avg_win_pct"],
        "avg_loss_pct":     metrics["avg_loss_pct"],
        "total_trades":     metrics["total_trades"],
        "curve_data":       metrics["curve_data"],
        "price_curve":      price_curve,
        "generated_at":     datetime.now(timezone.utc).isoformat(),
    }
