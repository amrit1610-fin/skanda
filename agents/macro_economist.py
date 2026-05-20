import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

# ── MTF Regime weights — higher timeframes have more authority ────────────────
MTF_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
MTF_WEIGHTS    = {"1m": 0.05, "5m": 0.10, "15m": 0.15, "1h": 0.25, "4h": 0.30, "1d": 0.15}
# Score map: positive = bullish bias, negative = bearish bias
REGIME_SCORES  = {
    "STRONG_BULLISH": +1.0,
    "BULLISH":        +0.6,
    "SIDEWAYS":        0.0,
    "BEARISH":        -0.6,
    "STRONG_BEARISH": -1.0,
    "UNKNOWN":         0.0,
}


class MacroEconomist:
    """
    Dual-mode macro intelligence:
      1. GMM clustering (existing) — trained on price history, used by server.py dashboard.
      2. MTF Regime Radar (new) — MA-stack classification across 6 timeframes,
         used by engine.py to gate live trades.
    """

    REGIME_NAME_MAP = {
        0: "Sideways / Mean Reversion",
        1: "Trend Breakout",
        2: "High Volatility / Chop",
    }

    def __init__(self):
        self.model = GaussianMixture(n_components=3, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
        self.cluster_to_regime = {}

    # ── Existing GMM methods (unchanged) ─────────────────────────────────────

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["daily_returns", "volatility_14", "momentum_50"])

        work = df.copy()
        if "close" not in work.columns:
            raise ValueError("Input dataframe must contain a 'close' column.")

        work["daily_returns"] = work["close"].pct_change()
        work["volatility_14"] = work["daily_returns"].rolling(14).std()
        sma_50 = work["close"].rolling(50).mean()
        work["momentum_50"] = (work["close"] - sma_50) / sma_50

        feats = work[["daily_returns", "volatility_14", "momentum_50"]]
        feats = feats.replace([np.inf, -np.inf], np.nan).dropna()
        return feats

    def _build_cluster_mapping(self, features: pd.DataFrame, cluster_labels: np.ndarray) -> dict:
        cluster_profiles = {}
        for cluster_id in range(3):
            subset = features.loc[cluster_labels == cluster_id]
            if subset.empty:
                cluster_profiles[cluster_id] = {"volatility_14": -1.0, "abs_momentum_50": -1.0}
                continue
            cluster_profiles[cluster_id] = {
                "volatility_14": float(subset["volatility_14"].mean()),
                "abs_momentum_50": float(subset["momentum_50"].abs().mean()),
            }

        high_vol_cluster = max(cluster_profiles, key=lambda c: cluster_profiles[c]["volatility_14"])
        remaining = [c for c in cluster_profiles if c != high_vol_cluster]
        trend_cluster = max(remaining, key=lambda c: cluster_profiles[c]["abs_momentum_50"])
        sideways_cluster = next(c for c in remaining if c != trend_cluster)

        return {
            sideways_cluster: 0,
            trend_cluster: 1,
            high_vol_cluster: 2,
        }

    def train_model(self, historical_df: pd.DataFrame) -> dict:
        features = self._prepare_features(historical_df)
        if len(features) < 80:
            raise ValueError("Not enough cleaned historical rows to train MacroEconomist (need at least 80).")

        x_scaled = self.scaler.fit_transform(features)
        cluster_labels = self.model.fit_predict(x_scaled)
        self.cluster_to_regime = self._build_cluster_mapping(features, cluster_labels)
        self.is_trained = True

        return {
            "status": "trained",
            "samples_used": int(len(features)),
            "cluster_mapping": self.cluster_to_regime,
        }

    def detect_current_regime(self, current_data_df: pd.DataFrame) -> dict:
        if not self.is_trained:
            raise RuntimeError("MacroEconomist model is not trained. Call train_model() first.")

        features = self._prepare_features(current_data_df)
        if features.empty:
            return {
                "regime_id": 0,
                "regime_name": self.REGIME_NAME_MAP[0],
                "confidence_pct": 0.0,
            }

        latest = features.tail(1)
        x_scaled = self.scaler.transform(latest)
        cluster_id = int(self.model.predict(x_scaled)[0])
        cluster_probs = self.model.predict_proba(x_scaled)[0]

        regime_id = int(self.cluster_to_regime.get(cluster_id, 0))
        confidence_pct = float(round(float(cluster_probs[cluster_id]) * 100.0, 2))
        regime_name = self.REGIME_NAME_MAP.get(regime_id, "Unknown")

        return {
            "regime_id": regime_id,
            "regime_name": regime_name,
            "confidence_pct": confidence_pct,
        }

    # ── NEW: Multi-Timeframe Regime Radar ────────────────────────────────────

    @staticmethod
    def _classify_tf_regime(df: pd.DataFrame) -> str:
        """
        Classifies a single timeframe's DataFrame using the EMA20/EMA50/SMA200 stack.

        Alignment rules (allowing for price to 'breathe' during pullbacks):
          EMA20 > EMA50 > SMA200 AND Price > EMA50  → STRONG_BULLISH
          EMA20 > EMA50 AND Price > EMA50           → BULLISH (SMA200 lagging)
          EMA20 < EMA50 < SMA200 AND Price < EMA50  → STRONG_BEARISH
          EMA20 < EMA50 AND Price < EMA50           → BEARISH
          Everything else                           → SIDEWAYS
        """
        if df is None or df.empty or "close" not in df.columns:
            return "UNKNOWN"

        # Need at least 30 rows for EMA50 to be meaningful
        if len(df) < 30:
            return "UNKNOWN"

        close = df["close"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        sma200 = close.rolling(200).mean()

        # Evaluate the most recent bar
        price  = float(close.iloc[-1])
        e20    = float(ema20.iloc[-1])
        e50    = float(ema50.iloc[-1])
        s200   = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None

        # Bullish stack (Trend remains intact as long as price holds above the 50 EMA baseline)
        if (e20 > e50) and (price > e50):
            if s200 is not None and e50 > s200:
                return "STRONG_BULLISH"
            return "BULLISH"

        # Bearish stack (Trend remains intact as long as price holds below the 50 EMA baseline)
        if (e20 < e50) and (price < e50):
            if s200 is not None and e50 < s200:
                return "STRONG_BEARISH"
            return "BEARISH"

        return "SIDEWAYS"

    def generate_regime_matrix(self, mtf_dataframes: dict) -> dict:
        """
        Evaluates market regime across all timeframes and returns a weighted macro score.

        Args:
            mtf_dataframes: dict mapping timeframe string → pd.DataFrame (OHLCV)
                            e.g. {"1m": df_1m, "5m": df_5m, ..., "1d": df_1d}

        Returns:
            {
              "matrix": {"1m": "BULLISH", "5m": "SIDEWAYS", ...},
              "overall_macro_score": 0.42,   # -1.0 (full bear) to +1.0 (full bull)
              "dominant_regime": "BULLISH",
            }
        """
        matrix = {}
        weighted_score = 0.0
        total_weight   = 0.0

        for tf in MTF_TIMEFRAMES:
            df = mtf_dataframes.get(tf)
            if df is None or df.empty:
                matrix[tf] = "UNKNOWN"
                continue

            regime = self._classify_tf_regime(df)
            matrix[tf] = regime

            weight = MTF_WEIGHTS.get(tf, 0.10)
            weighted_score += REGIME_SCORES[regime] * weight
            total_weight   += weight

        # Normalise to [-1.0, +1.0] even if some TFs were UNKNOWN (weight=0)
        if total_weight > 0:
            overall_macro_score = round(weighted_score / total_weight, 4)
        else:
            overall_macro_score = 0.0

        # Determine dominant label
        if overall_macro_score >= 0.5:
            dominant = "STRONG_BULLISH"
        elif overall_macro_score >= 0.15:
            dominant = "BULLISH"
        elif overall_macro_score <= -0.5:
            dominant = "STRONG_BEARISH"
        elif overall_macro_score <= -0.15:
            dominant = "BEARISH"
        else:
            dominant = "SIDEWAYS"

        return {
            "matrix":               matrix,
            "overall_macro_score":  overall_macro_score,
            "dominant_regime":      dominant,
        }
