import os
import pandas as pd
import joblib
from catboost import CatBoostClassifier

# Resolve model paths relative to THIS file so they work regardless of CWD
_CORE_DIR  = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.abspath(os.path.join(_CORE_DIR, '..', 'models'))
_DEFAULT_XGB_PATH = os.path.join(_MODEL_DIR, 'xgboost_btc_model.pkl')
_DEFAULT_CAT_PATH = os.path.join(_MODEL_DIR, 'catboost_model.cbm')

class SkandaInferenceEngine:
    def __init__(self,
                 xgb_path: str = _DEFAULT_XGB_PATH,
                 cat_path: str = _DEFAULT_CAT_PATH):
        # Load models into RAM once at startup to prevent I/O bottlenecks
        try:
            self.xgb_regime_model = joblib.load(xgb_path)

            self.catboost_prob_model = CatBoostClassifier(task_type='CPU')
            self.catboost_prob_model.load_model(cat_path)
            self.models_loaded = True
            print(f"[Core ML] Models loaded from {_MODEL_DIR}")
        except Exception as e:
            print(f"[Core ML] Warning: Failed to load ML models ({e}). Running in heuristic mode.")
            self.models_loaded = False

    def predict_regime(self, features: pd.DataFrame) -> int:
        """
        XGBoost Regime Filter: 1 = Trend, 0 = Chop.
        Used to strictly gate which strategies are allowed to fire.
        """
        if not self.models_loaded or features.empty:
            return 1 # Default to trend if models are missing
            
        # Assuming features DF is already formatted with RSI_14, Log_Ret_5, etc.
        predictions = self.xgb_regime_model.predict(features)
        return int(predictions[-1]) # Return the prediction for the most recent candle

    def calculate_win_probability(self, quant_signal: str, active_strategy: str, sentiment_score: float = 0.0) -> float:
        """
        CatBoost Probability Engine. 
        PRO FIX 2: sentiment_score is explicitly isolated and defaults to 0.0.
        If backtesting without FinBERT, the math gracefully ignores it.
        """
        if not self.models_loaded or quant_signal == "HOLD":
            return 0.0
            
        # Map strings to the categorical integers your CatBoost model expects
        # IMPORTANT: These must match the encoding used during training in core_logic/train_catboost.py
        signal_map = {"BUY": 1, "SELL": -1, "HOLD": 0, "STRONG BUY": 2, "STRONG SELL": -2}
        strategy_map = {
            # New canonical WOTA keys
            "ema_8_30":       0,
            "ema_9_15":       1,
            "trendline_break": 2,
            # Legacy aliases (safe fallbacks)
            "ema":            0,
            "rsi":            1,
            "trendline":      2,
            "bollinger":      0,
        }

        sig_val   = signal_map.get(quant_signal.upper(), 0)
        strat_val = strategy_map.get(active_strategy.lower(), 0)

        # Build the exact feature array CatBoost was trained on
        feature_vector = [sig_val, strat_val, sentiment_score]
        
        # Predict Probability of Class 1 (Win)
        prob = self.catboost_prob_model.predict_proba([feature_vector])[0][1]
        
        return round(prob * 100, 2)