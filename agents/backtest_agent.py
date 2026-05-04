"""
Historical simulation (~6 calendar months of bars) for a single symbol and strategy.
Uses the same `analyze(df)` interface as live `strategies/*` modules.
"""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

import numpy as np
import pandas as pd

# Months of history (calendar)
BACKTEST_MONTHS = 6

STRATEGY_MODULE_MAP: Dict[str, str] = {
    "ema": "strategies.ema",
    "rsi": "strategies.rsi_scalper",
    "bollinger": "strategies.bollingerband",
    "trendline": "strategies.trendline",
    "macd": "strategies.macd_momentum",
}

VALID_TIMEFRAMES = {"5m", "15m", "1h", "4h"}

# Approximate bars for BACKTEST_MONTHS days = 180
def _bars_for_timeframe(tf: str) -> int:
    days = 180
    if tf == "5m":
        return days * 24 * 12
    if tf == "15m":
        return days * 24 * 4
    if tf == "1h":
        return days * 24
    if tf == "4h":
        return days * 6
    return days * 24


def _strategy_fn(strategy: str) -> Callable[[pd.DataFrame], dict]:
    key = (strategy or "ema").lower().strip()
    mod_name = STRATEGY_MODULE_MAP.get(key)
    if not mod_name:
        mod_name = STRATEGY_MODULE_MAP["ema"]
    mod = importlib.import_module(mod_name)
    return getattr(mod, "analyze")


def _synthetic_ohlcv(symbol: str, n_bars: int, timeframe: str) -> pd.DataFrame:
    """Reproducible GBM-style OHLCV for offline backtests."""
    seed = int(hashlib.sha256(f"{symbol}:{timeframe}".encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.default_rng(seed)

    mu = 1.2e-5
    sigma = 0.012
    r = rng.normal(mu, sigma, n_bars)
    # Anchor scale by symbol hash
    base = 50.0 + (seed % 10000) / 100.0
    close = base * np.cumprod(1.0 + r)

    noise_hi = np.abs(rng.normal(0, 0.004, n_bars))
    noise_lo = np.abs(rng.normal(0, 0.004, n_bars))

    df = pd.DataFrame({
        "open": close * (1.0 + rng.uniform(-0.002, 0.002, n_bars)),
        "high": close * (1.0 + noise_hi),
        "low": close * (1.0 - noise_lo),
        "close": close,
        "volume": rng.integers(500, 8000, n_bars),
    })
    return df


def _signal_upper(res: dict) -> str:
    s = (res or {}).get("signal") or "HOLD"
    return str(s).upper()


def run_backtest(
    symbol: str,
    strategy: str,
    timeframe: str = "1h",
    months: int = BACKTEST_MONTHS,
    warmup: int = 120,
) -> Dict[str, Any]:
    """
    Simple bar-based backtest: enter on BUY/SELL from strategy; exit on opposite signal or flat.
    PnL recorded as fractional return on notional 1.0 per completed round-trip.
    """
    tf = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
    n_bars = _bars_for_timeframe(tf)
    # Scale bar count if user requests different months
    if months != BACKTEST_MONTHS:
        n_bars = int(round(n_bars * (months / BACKTEST_MONTHS)))

    df_full = _synthetic_ohlcv(symbol, n_bars, tf)
    analyze = _strategy_fn(strategy)

    position: str | None = None
    entry_price: float | None = None
    trades: List[Dict[str, Any]] = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0

    start_i = max(warmup, 2)

    for i in range(start_i, len(df_full)):
        window = df_full.iloc[: i + 1].copy()
        try:
            out = analyze(window)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Strategy error at bar {i}: {exc}",
                "symbol": symbol,
                "strategy": strategy,
                "timeframe": tf,
            }

        sig = _signal_upper(out)
        px = float(window.iloc[-1]["close"])

        if position is None:
            if sig == "BUY":
                position = "LONG"
                entry_price = px
            elif sig == "SELL":
                position = "SHORT"
                entry_price = px
            continue

        if position == "LONG" and sig == "SELL" and entry_price:
            pnl = (px - entry_price) / entry_price
            trades.append({
                "side": "LONG",
                "entry": round(entry_price, 6),
                "exit": round(px, 6),
                "pnl": round(pnl, 6),
            })
            equity *= 1.0 + pnl
            position = "SHORT"
            entry_price = px
        elif position == "SHORT" and sig == "BUY" and entry_price:
            pnl = (entry_price - px) / entry_price
            trades.append({
                "side": "SHORT",
                "entry": round(entry_price, 6),
                "exit": round(px, 6),
                "pnl": round(pnl, 6),
            })
            equity *= 1.0 + pnl
            position = "LONG"
            entry_price = px
        elif position == "LONG" and sig == "BUY":
            continue
        elif position == "SHORT" and sig == "SELL":
            continue

        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Close open position at last close
    if position and entry_price is not None:
        last_px = float(df_full.iloc[-1]["close"])
        if position == "LONG":
            pnl = (last_px - entry_price) / entry_price
        else:
            pnl = (entry_price - last_px) / entry_price
        trades.append({
            "side": position,
            "entry": round(entry_price, 6),
            "exit": round(last_px, 6),
            "pnl": round(pnl, 6),
        })
        equity *= 1.0 + pnl

    completed = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in completed if t["pnl"] > 0]
    losses = [t for t in completed if t["pnl"] < 0]
    win_rate = (len(wins) / len(completed) * 100.0) if completed else 0.0

    rets = [t["pnl"] for t in completed]
    sharpe = 0.0
    if len(rets) > 1:
        m = float(np.mean(rets))
        s = float(np.std(rets))
        sharpe = float(m / s * np.sqrt(252)) if s > 1e-12 else 0.0

    return {
        "ok": True,
        "symbol": symbol,
        "strategy": strategy.lower().strip(),
        "timeframe": tf,
        "months": months,
        "bars": n_bars,
        "total_trades": len(completed),
        "win_rate_percent": round(win_rate, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_percent": round(max_dd * 100.0, 2),
        "final_equity_multiple": round(equity, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trades_sample": completed[:50],
    }
