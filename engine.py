import time
import os
from core_logic.strategies import get_signal_for_strategy
from core_logic.ml_inference import SkandaInferenceEngine
from agents.macro_economist import MacroEconomist

# Initialize core inference engine once
ml_engine     = SkandaInferenceEngine()
macro_brain   = MacroEconomist()

def run_trading_cycle(agents, mode="live"):
    """
    A single iteration of the Skanda trading loop.
    Identical logic for both Live and Backtest modes.
    """
    try:
        # 1. Fetch Data (Universal Faucet)
        # Returns standard_payload dict including mtf_data
        market_data_response = agents['data'].fetch_market_data()
        market_data = market_data_response.get("data", {})
        df = market_data.get("ohlcv_data")

        if df is None or df.empty:
            return  # Skip cycle if no data

        mtf_data = market_data.get("mtf_data", {})
        
        # 2. Quant Analysis (Shared Math)
        # Bypasses LLM agent for speed; uses core_logic directly
        active_policy = agents['data']._read_policy()
        strategy_name = active_policy.get("strategy", "ema_8_30")

        quant_signal = get_signal_for_strategy(df, strategy_name)

        if quant_signal == "HOLD":
            return  # No action needed

        # 3. MTF Regime Radar (Macro Filter)
        # Evaluates 6 timeframes via the MacroEconomist shared brain
        mtf_data = market_data.get("mtf_data", {})
        regime_result = macro_brain.generate_regime_matrix(mtf_data)
        macro_score    = regime_result.get("overall_macro_score", 0.0)
        regime_matrix  = regime_result.get("matrix", {})
        dominant       = regime_result.get("dominant_regime", "SIDEWAYS")

        # 4. Sentiment Analysis
        sentiment_score = 0.0
        dynamic_text = f"Market action for {market_data['symbol']} showing patterns."
        sentiment_payload = agents['sentiment'].act("analyze_sentiment", {"text": dynamic_text})
        sentiment_score = sentiment_payload.get("data", {}).get("sentiment_score", 0.0)

        # 5. ML Validation (Shared Inference)
        # Uses the SkandaInferenceEngine we built in core_logic
        win_prob = ml_engine.calculate_win_probability(
            quant_signal=quant_signal,
            active_strategy=strategy_name,
            sentiment_score=sentiment_score
        )

        # 6. Risk Management (Logic Gate)
        # This determines if the trade is actually sent to the trader
        trade_proposal = {
            "symbol":          market_data['symbol'],
            "signal_type":     quant_signal,
            "strategy_used":   strategy_name,
            "win_probability": win_prob,
            "sentiment_score": sentiment_score,
            "current_price":   float(df.iloc[-1]['close']),
            # MTF Regime fields — consumed by process_proposal() in RiskManager
            "macro_score":     macro_score,
            "regime_matrix":   regime_matrix,
            "dominant_regime": dominant,
        }

        # Risk manager checks probability threshold + Macro Trend veto
        is_approved = agents['risk'].process_proposal(trade_proposal)

        # 7. Execution (Universal Broker)
        if is_approved:
            # Force paper mode if running a backtest, otherwise read UI toggle
            if mode == "backtest":
                is_paper = True
            else:
                is_paper = active_policy.get("is_paper_trading", True)
            
            # Pass the explicit flag to the trader
            agents['trader'].execute_trade(trade_proposal, market_data, is_paper=is_paper)

    except Exception as e:
        print(f"[engine] Error in trading cycle: {e}")