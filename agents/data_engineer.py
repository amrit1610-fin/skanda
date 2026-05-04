import os
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
from .base_agent import ReActAgent
from .asset_manager import UNIVERSE

REAL_SYMBOL = "BTCUSDT"
VALID_TIMEFRAMES = {"5m", "15m", "1h", "4h"}

# Timeframe → number of OHLCV candles to simulate (primary & multi-coin panels)
TF_CANDLES = {"5m": 288, "15m": 96, "1h": 168, "4h": 90}


def _mock_ohlcv_for_symbol(symbol: str, n_candles: int, timeframe: str) -> pd.DataFrame:
    """Deterministic-per-symbol mock OHLCV so multi-coin correlation structure is stable run-to-run."""
    seed = int(hashlib.sha256(f"{symbol}:{timeframe}:{n_candles}".encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.default_rng(seed)

    base_price = 20000.0 + (seed % 50000) / 10.0
    pct_moves = rng.normal(0, 0.008, n_candles)
    closes = base_price * np.cumprod(1 + pct_moves)

    return pd.DataFrame({
        "open": closes * (1 + rng.uniform(-0.002, 0.002, n_candles)),
        "high": closes * (1 + np.abs(rng.normal(0, 0.004, n_candles))),
        "low": closes * (1 - np.abs(rng.normal(0, 0.004, n_candles))),
        "close": closes,
        "volume": rng.integers(500, 5000, n_candles),
    })


class DataEngineer(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), "..", ".skills", "data_engineer", "system_prompt.md")
        super().__init__("DataEngineer", skill_path)

    def _read_policy(self) -> dict:
        """Read the full active_policy.json, returning safe defaults on failure."""
        try:
            policy_path = os.path.join(os.path.dirname(__file__), "..", "config", "active_policy.json")
            with open(policy_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _get_active_symbol(self) -> str:
        return self._read_policy().get("symbol", REAL_SYMBOL)

    def _get_timeframe(self) -> str:
        tf = self._read_policy().get("timeframe", "5m")
        return tf if tf in VALID_TIMEFRAMES else "5m"

    def _fetch_one_symbol(self, symbol: str, n_candles: int, timeframe: str) -> tuple[str, pd.DataFrame]:
        return symbol, _mock_ohlcv_for_symbol(symbol, n_candles, timeframe)

    def fetch_market_data(self):
        """Fetches OHLCV for the full universe in parallel; primary symbol drives the main panel."""
        symbol = self._get_active_symbol()
        timeframe = self._get_timeframe()
        n_candles = TF_CANDLES.get(timeframe, 288)

        self.think(
            f"Fetching {n_candles} {timeframe} OHLCV candles for {len(UNIVERSE)} symbols in parallel "
            f"(primary: {symbol})..."
        )

        ohlcv_by_symbol: dict[str, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=min(10, len(UNIVERSE))) as ex:
            futures = {
                ex.submit(self._fetch_one_symbol, sym, n_candles, timeframe): sym
                for sym in UNIVERSE
            }
            for fut in as_completed(futures):
                sym, df = fut.result()
                ohlcv_by_symbol[sym] = df

        primary_df = ohlcv_by_symbol.get(symbol) or ohlcv_by_symbol.get(REAL_SYMBOL)
        if primary_df is None:
            primary_df = next(iter(ohlcv_by_symbol.values()))

        macro_news = {
            "summary": "Markets are volatile due to recent inflation data. Crypto showing resilience.",
            "sentiment": "neutral-bullish",
        }

        standard_payload = {
            "symbol": symbol,
            "exchange": "delta_india",
            "timeframe": timeframe,
            "ohlcv_data": primary_df,
            "ohlcv_by_symbol": ohlcv_by_symbol,
            "universe": UNIVERSE,
            "macro_news": macro_news,
        }

        return self.act("fetch_market_data", standard_payload)
