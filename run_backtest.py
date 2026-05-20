"""
run_backtest.py — Skanda WOTA Standalone Backtest Runner

Usage:
    python run_backtest.py

Edit the parameters at the bottom of this file to change the simulation.
This script fetches real historical OHLCV data directly from Binance via CCXT (no CSVs),
then replays it through the same engine.py logic as the live bot.
"""
from __future__ import annotations

import pandas as pd
import ccxt

from agents.data_engineer import DataEngineer
from agents.quant_trader import QuantTrader
from agents.risk_manager import RiskManager
from agents.sentiment_analyst import SentimentAnalyst
from engine import run_trading_cycle


# ─── CCXT Data Fetcher ────────────────────────────────────────────────────────

def fetch_memory_ohlcv(symbol: str, timeframe: str, months: int) -> pd.DataFrame:
    """
    Fetches historical OHLCV data directly from Binance into RAM using CCXT pagination.
    DO NOT REMOVE: No CSV files required — data lives only in process memory.

    Returns a DataFrame with columns: timestamp, open, high, low, close, volume
    where timestamp is a UTC-aware datetime64.
    """
    print(f"[*] Fetching {months} months of {timeframe} data for {symbol} via CCXT...")
    exchange = ccxt.binance({'enableRateLimit': True})

    days = months * 30
    bar_counts = {
        "5m":  days * 24 * 12,
        "15m": days * 24 * 4,
        "1h":  days * 24,
        "4h":  days * 6,
    }
    n_bars = bar_counts.get(timeframe, days * 24)

    tf_ms_map = {
        "5m":  300_000,
        "15m": 900_000,
        "1h":  3_600_000,
        "4h":  14_400_000,
    }
    ms_per_candle = tf_ms_map.get(timeframe, 3_600_000)

    # Ensure ccxt-compatible symbol format (e.g. BTCUSDT → BTC/USDT)
    ccxt_sym = (
        symbol.replace("USDT", "/USDT")
        if "USDT" in symbol and "/" not in symbol
        else symbol
    )

    all_ohlcv: list = []
    since = exchange.milliseconds() - (n_bars * ms_per_candle)

    while len(all_ohlcv) < n_bars:
        try:
            bars = exchange.fetch_ohlcv(ccxt_sym, timeframe, since=since, limit=1000)
            if not bars:
                break
            all_ohlcv.extend(bars)
            since = bars[-1][0] + 1  # advance to next candle
        except Exception as exc:
            print(f"[!] CCXT fetch error: {exc}")
            break

    if not all_ohlcv:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(
        all_ohlcv[-n_bars:],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    print(f"[+] Loaded {len(df)} candles into memory.")
    return df


# ─── Backtest Runner ──────────────────────────────────────────────────────────

def start_backtest(symbol: str, timeframe: str, strategy: str, months: int) -> None:
    # 1. Initialise agents (shared brains, backtest driver)
    data_agent     = DataEngineer()
    trader_agent   = QuantTrader()
    risk_agent     = RiskManager()
    # SentimentAnalyst bypassed in backtest to avoid FinBERT latency and API costs;
    # engine.py injects sentiment_score=0.0 when mode=="backtest"
    sentiment_agent = SentimentAnalyst()

    agents = {
        "data":      data_agent,
        "trader":    trader_agent,
        "risk":      risk_agent,
        "sentiment": sentiment_agent,
    }

    # 2. Fetch real historical data directly into RAM
    df = fetch_memory_ohlcv(symbol, timeframe, months)
    if df.empty:
        print(f"\n[!] Failed to fetch data for {symbol}. Exiting.")
        return

    # 3. Prime the DataEngineer Time Machine
    data_agent.load_backtest_data({symbol: df})

    # 4. Patch policy so engine.py reads these variables, not the live JSON file
    data_agent._read_policy = lambda: {
        "strategy":  strategy,
        "timeframe": timeframe,
        "symbol":    symbol,
    }

    # 5. Execution loop — identical logic to the live bot
    print(f"\n--- Starting Backtest: {symbol} | {strategy} | {timeframe} | {months}m ---\n")
    start_time = pd.Timestamp.now()
    cycle_count = 0

    try:
        while True:
            run_trading_cycle(agents, mode="backtest")
            cycle_count += 1
    except StopIteration:
        duration = pd.Timestamp.now() - start_time
        print(f"\n--- Backtest Complete ---")
        print(f"Candles replayed : {cycle_count}")
        print(f"Time taken       : {duration}")

    # 6. Report results
    logs = trader_agent.get_backtest_logs()
    executed = [t for t in logs if t.get("status") == "backtest_executed"]
    print(f"\nTotal executed trades : {len(executed)}")

    if executed:
        final_bal = executed[-1].get("mock_balance_usdt", 10_000)
        print(f"Final mock balance    : ${final_bal:,.2f} USDT")

        wins   = [t for t in executed if (t.get("pnl") or 0) > 0]
        losses = [t for t in executed if (t.get("pnl") or 0) < 0]
        win_rate = len(wins) / len(executed) * 100 if executed else 0
        print(f"Win rate              : {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
    else:
        print("No trades were executed during this backtest.")


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # =========================================================
    # ⚙️  BACKTEST PARAMETERS — edit these to change simulation
    # =========================================================
    TARGET_SYMBOL    = "BTCUSDT"
    TARGET_TIMEFRAME = "1h"       # Options: "5m", "15m", "1h", "4h"
    TARGET_STRATEGY  = "ema_8_30" # Options: "ema_8_30", "ema_9_15", "trendline_break"
    TARGET_MONTHS    = 1          # Number of months of history to replay
    # =========================================================

    start_backtest(
        symbol=TARGET_SYMBOL,
        timeframe=TARGET_TIMEFRAME,
        strategy=TARGET_STRATEGY,
        months=TARGET_MONTHS,
    )
