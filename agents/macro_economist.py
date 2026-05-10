import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler


class MacroEconomist:
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
