"""
Multi-asset intelligence: lead–lag structure via cross-correlation of returns
across the configured universe. Replaces the former SelectionEngineer role.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from .base_agent import ReActAgent

# Canonical watchlist (USDT perpetual-style symbols as used elsewhere in the stack)
UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT",
    "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "ADAUSDT",
]


class AssetManager(ReActAgent):
    def __init__(self):
        super().__init__("AssetManager")

    @staticmethod
    def _log_returns(close: pd.Series) -> np.ndarray:
        r = np.log(close.astype(float)).diff().dropna()
        return r.values.astype(float)

    def identify_lead_lag(
        self,
        ohlcv_by_symbol: Dict[str, pd.DataFrame],
        max_lag: int = 8,
        min_overlap: int = 64,
    ) -> Dict[str, Any]:
        """
        For each ordered pair (leader, follower), estimate best lag τ such that
        corr(r_leader[t], r_follower[t+τ]) is maximized. τ > 0 ⇒ follower lags leader.
        """
        self.think(
            f"Identifying lead–lag structure across {len(ohlcv_by_symbol)} symbols "
            f"(max_lag={max_lag})..."
        )

        symbols = [s for s in UNIVERSE if s in ohlcv_by_symbol and ohlcv_by_symbol[s] is not None]
        if len(symbols) < 2:
            return {
                "universe": UNIVERSE,
                "pairs": [],
                "note": "Insufficient multi-coin data for lead–lag analysis.",
                "agent": "AssetManager",
            }

        rets: Dict[str, np.ndarray] = {}
        for sym in symbols:
            df = ohlcv_by_symbol[sym]
            if df is None or df.empty or "close" not in df.columns:
                continue
            arr = self._log_returns(df["close"])
            if len(arr) >= min_overlap:
                rets[sym] = arr

        usable = list(rets.keys())
        if len(usable) < 2:
            return {
                "universe": UNIVERSE,
                "pairs": [],
                "note": "Not enough overlapping returns.",
                "agent": "AssetManager",
            }

        pairs: list[dict[str, Any]] = []

        def _corr_at_lag(a: np.ndarray, b: np.ndarray, lag: int) -> float | None:
            """corr(a[:-lag or None], b[lag:]) for lag>=0 meaning b lags a."""
            if lag < 0 or lag > max_lag:
                return None
            if lag == 0:
                n = min(len(a), len(b))
                x, y = a[-n:], b[-n:]
            else:
                if len(a) <= lag or len(b) <= lag:
                    return None
                x = a[:-lag]
                y = b[lag:]
            n = min(len(x), len(y))
            if n < min_overlap:
                return None
            x = x[-n:]
            y = y[-n:]
            if np.std(x) < 1e-12 or np.std(y) < 1e-12:
                return None
            return float(np.corrcoef(x, y)[0, 1])

        for i, sym_a in enumerate(usable):
            for j, sym_b in enumerate(usable):
                if i == j:
                    continue
                a, b = rets[sym_a], rets[sym_b]
                best_lag = 0
                best_r = -2.0
                for tau in range(0, max_lag + 1):
                    c = _corr_at_lag(a, b, tau)
                    if c is not None and c > best_r:
                        best_r = c
                        best_lag = tau
                if best_r <= -2.0:
                    continue
                pairs.append({
                    "leader": sym_a,
                    "follower": sym_b,
                    "best_lag_bars": best_lag,
                    "correlation": round(best_r, 4),
                    "interpretation": (
                        f"{sym_b} lags {sym_a} by ~{best_lag} bar(s)"
                        if best_lag > 0
                        else f"{sym_a} and {sym_b} contemporaneous (lag 0)"
                    ),
                })

        pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)

        return {
            "universe": UNIVERSE,
            "symbols_used": usable,
            "max_lag": max_lag,
            "top_pairs": pairs[:20],
            "pair_count": len(pairs),
            "agent": "AssetManager",
        }

    def analyze(self, ohlcv_by_symbol: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        payload = self.identify_lead_lag(ohlcv_by_symbol)
        return self.act("identify_lead_lag", payload)
