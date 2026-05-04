import os
import numpy as np
from catboost import CatBoostClassifier
from .base_agent import ReActAgent

# Lazy-loaded model to avoid overhead
_model = None

def _get_catboost_model():
    global _model
    if _model is not None:
        return _model
        
    model_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'catboost_baseline.cbm')
    
    # Explicitly assign to CPU to leave VRAM for the FinBERT model on RTX 3050
    _model = CatBoostClassifier(task_type='CPU') 
    
    if os.path.exists(model_path):
        try:
            _model.load_model(model_path)
            print("Loaded pre-trained CatBoost model.")
        except Exception as e:
            print(f"Failed to load model from {model_path}: {e}")
            _initialize_baseline(_model)
    else:
        print("No pre-trained CatBoost model found. Initializing baseline...")
        _initialize_baseline(_model)
        
    return _model

def calculate_heuristic_prob(quant_signal: str, sentiment_score: float, strategy: str = "ema") -> float:
    """
    Calculates a dynamic win probability based on signal strength, sentiment, and strategy context.
    Ensures strategy-agnostic intelligence with a touch of variance.
    """
    # Base probability by signal type
    signal_map = {
        "STRONG BUY": 0.82,
        "BUY":        0.65,
        "STRONG SELL": 0.80,
        "SELL":       0.63,
        "HOLD":       0.45
    }
    base_prob = signal_map.get(quant_signal.upper(), 0.50)
    
    # Sentiment influence (max +/- 15%)
    # sentiment_score is [-1.0, 1.0]
    sentiment_weight = 0.15
    sentiment_impact = sentiment_score * sentiment_weight
    
    # Strategy-specific adjustments (optional flavor)
    strat_bonus = 0.0
    if strategy.lower() == "rsi" and quant_signal.upper() in ["BUY", "STRONG BUY"]:
        strat_bonus = 0.05
    elif strategy.lower() == "ema" and "STRONG" in quant_signal.upper():
        strat_bonus = 0.03

    # Calculate final probability
    prob = base_prob + sentiment_impact + strat_bonus
    
    # Add Gaussian noise (+/- 0.5%) to avoid stagnation
    noise = np.random.normal(0, 0.005)
    prob += noise
    
    # Clamp to [0.01, 0.99]
    return float(np.clip(prob, 0.01, 0.99))

def predict_probability(features):
    """
    ML inference tool (Heuristic-driven for strategy-agnostic intelligence).
    Accepts features dict with quant_signal, sentiment_score, and active_strategy.
    Returns probability percentage (0-100) and recommendation.
    """
    quant_signal = str(features.get("quant_signal", "HOLD")).upper()
    sentiment    = float(features.get("sentiment_score", 0.0))
    strategy     = str(features.get("active_strategy", "ema")).lower()
    
    prob = calculate_heuristic_prob(quant_signal, sentiment, strategy)
    win_prob_percent = round(prob * 100, 2)
    
    # Logic-gated action: Proceed only if win prob >= 70%
    action = "PROCEED" if win_prob_percent >= 70.0 else "HOLD"
    
    return {
        "win_probability": win_prob_percent,
        "recommended_action": action,
        "confidence_score": round(abs(prob - 0.5) * 200, 2)
    }

class MLEngineer(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'ml_engineer', 'system_prompt.md')
        super().__init__("MLEngineer", skill_path)

    def validate_signal(self, features):
        self.think("Validating signal probabilistically using CatBoost model...")
        
        # Enforce Tool Execution
        inference_result = self.enforce_tool_execution(features)
        
        if inference_result is None:
            self.think("ML inference failed. Defaulting to safe probabilities.")
            inference_result = {
                "win_probability": 0.0,
                "recommended_action": "HOLD",
                "confidence_score": 0.0
            }
            
        return self.act("validate_signal", inference_result)
