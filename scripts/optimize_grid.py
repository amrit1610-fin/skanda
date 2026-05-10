"""
Standalone research utility: brute-force grid search over z-entry thresholds for a
BTC/ETH spread (mock OHLCV via DataEngineer-style generator). Does not import or
modify live trading agents beyond `calculate_vectorized_backtest` in backtest_agent.
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Repo root on sys.path when run as: python scripts/optimize_grid.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.backtest_agent import calculate_vectorized_backtest  # noqa: E402
from agents.data_engineer import DataEngineer  # noqa: E402
import agents.data_engineer as data_engineer_mod  # noqa: E402

# ~3 months of 1h bars
TIMEFRAME = "1h"
N_BARS_3M = int(90 * 24)
SYMBOL_Y = "BTCUSDT"
SYMBOL_X = "ETHUSDT"


def run_parameter_grid_search(historical_df, backtest_function, param_grid):
    """
    Executes a brute-force parameter optimization grid.

    param_grid example:
    {
        'z_entry_threshold': [1.5, 2.0, 2.5, 3.0],
        'half_life_decay': [5, 15, 30, 60],
        'fee_pct': [0.001]
    }
    """
    keys = param_grid.keys()
    combinations = [dict(zip(keys, v)) for v in itertools.product(*param_grid.values())]

    print(f"[Optimizer] Initiating Grid Search: {len(combinations)} combinations...")
    results_log = []

    start_time = time.time()

    for params in combinations:
        try:
            metrics = backtest_function(historical_df, **params)
            results_log.append({
                **params,
                "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                "total_return_pct": metrics.get("total_return_pct", 0),
                "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
            })
        except Exception:
            pass

    if not results_log:
        print("[Optimizer] No successful runs (all combinations failed).")
        return []

    df_results = pd.DataFrame(results_log)
    df_results = df_results.sort_values(by="sharpe_ratio", ascending=False).reset_index(drop=True)

    execution_time = round(time.time() - start_time, 2)
    print(f"[Optimizer] Completed in {execution_time} seconds.")

    return df_results.head(10).to_dict(orient="records")


def fetch_pair_history_three_months() -> pd.DataFrame:
    """
    Build ~3 months of aligned 1h mock OHLCV for BTCUSDT (Y) and ETHUSDT (X)
    using the same generator as DataEngineer (deterministic per symbol).
    Instantiates DataEngineer to satisfy the research pipeline hook.
    """
    _engineer = DataEngineer()
    _ = _engineer  # reference retained for explicit use of DataEngineer in this script

    btc = data_engineer_mod._mock_ohlcv_for_symbol(SYMBOL_Y, N_BARS_3M, TIMEFRAME)
    eth = data_engineer_mod._mock_ohlcv_for_symbol(SYMBOL_X, N_BARS_3M, TIMEFRAME)

    n = min(len(btc), len(eth))
    btc = btc.iloc[-n:].reset_index(drop=True)
    eth = eth.iloc[-n:].reset_index(drop=True)

    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({
        "timestamp": idx,
        "close_btc": btc["close"].astype(float).values,
        "close_eth": eth["close"].astype(float).values,
    })


def _hedge_ratio(y: np.ndarray, x: np.ndarray) -> float:
    """OLS slope Y ~ X (no constant) for spread; guards var(x)==0."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    vx = np.var(x)
    if vx < 1e-18 or not np.isfinite(vx):
        raise ValueError("zero_or_invalid_var_x")
    cov = np.mean((x - x.mean()) * (y - y.mean()))
    h = cov / vx
    if not np.isfinite(h):
        raise ValueError("invalid_hedge")
    return float(h)


def build_zscore_signal_df(
    historical_pair_df: pd.DataFrame,
    z_entry_threshold: float,
) -> pd.DataFrame:
    """
    Mock pairs signal: spread = BTC - h*ETH, z-score spread; |z| > threshold → directional
    trade in BTC (Y): z > entry → short (-1), z < -entry → long (1).
    """
    y = historical_pair_df["close_btc"].astype(float).values
    x = historical_pair_df["close_eth"].astype(float).values
    h = _hedge_ratio(y, x)
    spread = y - h * x
    std = float(np.std(spread, ddof=0))
    if std < 1e-12 or not np.isfinite(std):
        raise ValueError("spread_std_zero")
    z = (spread - float(np.mean(spread))) / std
    sig = np.zeros(len(z), dtype=float)
    sig[z > z_entry_threshold] = -1.0
    sig[z < -z_entry_threshold] = 1.0

    out = pd.DataFrame({
        "timestamp": historical_pair_df["timestamp"].values,
        "close": y,
        "signal": sig,
    })
    return out


def run_zscore_vectorized_backtest(historical_pair_df: pd.DataFrame, **params) -> dict:
    """Adapter: build signals from z-entry + fee, then vectorized backtest."""
    z_entry = float(params["z_entry_threshold"])
    fee_pct = float(params.get("fee_pct", 0.001))
    df_bt = build_zscore_signal_df(historical_pair_df, z_entry)
    return calculate_vectorized_backtest(
        df_bt,
        signal_col="signal",
        price_col="close",
        fee_pct=fee_pct,
    )


def print_top_five_table(df: pd.DataFrame) -> None:
    if df.empty:
        return
    top = df.head(5).copy()
    # Prefer column order for readability
    preferred = [
        "z_entry_threshold",
        "fee_pct",
        "sharpe_ratio",
        "total_return_pct",
        "max_drawdown_pct",
    ]
    ordered = [c for c in preferred if c in top.columns] + [
        c for c in top.columns if c not in preferred
    ]
    top = top[ordered]
    print("\n" + "=" * 72)
    print(" Top 5 parameter combinations (by sharpe_ratio)")
    print("=" * 72)
    print(top.to_string(index=False))
    print("=" * 72 + "\n")


def main():
    historical_df = fetch_pair_history_three_months()
    print(
        f"[Data] Loaded mock pair history: {SYMBOL_Y} vs {SYMBOL_X}, "
        f"n={len(historical_df)} bars ({TIMEFRAME}, ~3 months)"
    )

    param_grid = {
        "z_entry_threshold": [1.5, 2.0, 2.5, 3.0],
        "fee_pct": [0.001],
    }

    top_records = run_parameter_grid_search(
        historical_df,
        run_zscore_vectorized_backtest,
        param_grid,
    )
    if not top_records:
        return
    df_out = pd.DataFrame(top_records)
    print_top_five_table(df_out)


if __name__ == "__main__":
    main()
