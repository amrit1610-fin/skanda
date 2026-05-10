"""
Multi-asset intelligence: statistical cointegration (Engle–Granger) and spread z-scores
across the configured universe. Replaces correlation-only lead–lag ranking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_agent import ReActAgent

try:
    import statsmodels.api as sm
    from statsmodels.tsa.stattools import coint as _coint
except ImportError:  # graceful if statsmodels missing in env
    sm = None  # type: ignore
    _coint = None  # type: ignore

# Canonical watchlist (USDT perpetual-style symbols as used elsewhere in the stack)
UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT",
    "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "ADAUSDT",
]

_MIN_BARS_COINT = 64


def analyze_cointegration_pair(price_series_y, price_series_x, p_value_threshold=0.05):
    """
    Analyzes two price series for Cointegration and calculates the Spread Z-Score.
    Returns: Dict with z_score, p_value, and hedge_ratio, or not cointegrated.
    """
    if _coint is None or sm is None:
        return {"is_cointegrated": False, "p_value": None, "note": "statsmodels_unavailable"}

    try:
        sy = pd.Series(price_series_y, dtype=float).dropna()
        sx = pd.Series(price_series_x, dtype=float).dropna()
        n = min(len(sy), len(sx))
        if n < _MIN_BARS_COINT:
            return {"is_cointegrated": False, "p_value": None, "note": "insufficient_length"}

        sy = sy.iloc[-n:].reset_index(drop=True)
        sx = sx.iloc[-n:].reset_index(drop=True)

        _, p_value, _ = _coint(sy.values, sx.values)
        p_value = float(p_value)
        if not np.isfinite(p_value) or p_value > p_value_threshold:
            return {"is_cointegrated": False, "p_value": round(p_value, 4) if np.isfinite(p_value) else None}

        X = sm.add_constant(sx.values)
        model = sm.OLS(sy.values, X).fit()
        hedge_ratio = float(model.params[1])

        spread = sy - (hedge_ratio * sx)
        std = float(spread.std())
        if std < 1e-12 or not np.isfinite(std):
            return {"is_cointegrated": False, "p_value": round(p_value, 4), "note": "spread_degenerate"}

        z_score_series = (spread - spread.mean()) / spread.std()
        current_z_score = float(z_score_series.iloc[-1])

        return {
            "is_cointegrated": True,
            "p_value": round(p_value, 4),
            "hedge_ratio": round(hedge_ratio, 4),
            "current_z_score": round(current_z_score, 3),
        }
    except Exception as exc:
        return {"is_cointegrated": False, "p_value": None, "error": str(exc)[:120]}


def _align_close_pair(
    sym_y: str,
    sym_x: str,
    ohlcv_by_symbol: Dict[str, pd.DataFrame],
) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    dy = ohlcv_by_symbol.get(sym_y)
    dx = ohlcv_by_symbol.get(sym_x)
    if dy is None or dx is None or dy.empty or dx.empty:
        return None, None
    if "close" not in dy.columns or "close" not in dx.columns:
        return None, None
    n = min(len(dy), len(dx))
    if n < _MIN_BARS_COINT:
        return None, None
    y = dy["close"].iloc[-n:].astype(float).reset_index(drop=True)
    x = dx["close"].iloc[-n:].astype(float).reset_index(drop=True)
    return y, x


class AssetManager(ReActAgent):
    def __init__(self):
        super().__init__("AssetManager")
        self._cointegrated_pairs: List[Dict[str, Any]] = []
        self._cointegration_by_symbol_y: Dict[str, Dict[str, Any]] = {}

    def identify_lead_lag(
        self,
        ohlcv_by_symbol: Dict[str, pd.DataFrame],
        p_value_threshold: float = 0.05,
    ) -> Dict[str, Any]:
        """
        Scan ordered pairs in the universe for Engle–Granger cointegration; retain spread z-score
        and hedge ratio per pair. Exposes ``cointegration_by_symbol_y`` for the Quant Analyst (Y = leg traded).
        """
        self.think(
            f"Cointegration scan across universe (p<{p_value_threshold}) — "
            f"{len(ohlcv_by_symbol)} symbols in panel..."
        )

        symbols = [
            s for s in UNIVERSE
            if s in ohlcv_by_symbol and ohlcv_by_symbol[s] is not None and not ohlcv_by_symbol[s].empty
        ]
        if len(symbols) < 2:
            self._cointegrated_pairs = []
            self._cointegration_by_symbol_y = {}
            return {
                "universe": UNIVERSE,
                "symbols_used": symbols,
                "cointegrated_pairs": [],
                "cointegration_by_symbol_y": {},
                "pair_count": 0,
                "note": "Insufficient multi-coin data for cointegration analysis.",
                "agent": "AssetManager",
                "method": "engle_granger_cointegration",
                "top_pairs": [],
            }

        cointegrated_pairs: List[Dict[str, Any]] = []

        for sym_y in symbols:
            for sym_x in symbols:
                if sym_y == sym_x:
                    continue
                y_series, x_series = _align_close_pair(sym_y, sym_x, ohlcv_by_symbol)
                if y_series is None:
                    continue
                try:
                    res = analyze_cointegration_pair(y_series, x_series, p_value_threshold=p_value_threshold)
                except Exception:
                    continue
                if not res.get("is_cointegrated"):
                    continue
                cointegrated_pairs.append({
                    "asset_y": sym_y,
                    "asset_x": sym_x,
                    "is_cointegrated": True,
                    "p_value": res.get("p_value"),
                    "hedge_ratio": res.get("hedge_ratio"),
                    "current_z_score": res.get("current_z_score"),
                })

        cointegrated_pairs.sort(
            key=lambda p: float(p["p_value"]) if p.get("p_value") is not None else 1.0
        )

        by_y: Dict[str, Dict[str, Any]] = {}
        for entry in cointegrated_pairs:
            y = entry["asset_y"]
            pv = entry.get("p_value")
            if pv is None:
                continue
            if y not in by_y or pv < (by_y[y].get("p_value") or 1.0):
                by_y[y] = dict(entry)

        self._cointegrated_pairs = cointegrated_pairs[:50]
        self._cointegration_by_symbol_y = by_y

        return {
            "universe": UNIVERSE,
            "symbols_used": symbols,
            "cointegrated_pairs": self._cointegrated_pairs,
            "cointegration_by_symbol_y": self._cointegration_by_symbol_y,
            "pair_count": len(cointegrated_pairs),
            "agent": "AssetManager",
            "method": "engle_granger_cointegration",
            "top_pairs": self._cointegrated_pairs[:20],
        }

    def analyze(self, ohlcv_by_symbol: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        payload = self.identify_lead_lag(ohlcv_by_symbol)
        return self.act("identify_lead_lag", payload)
