import time
import json
import os
from datetime import datetime

from agents.user_proxy import UserProxy
from agents.data_engineer import DataEngineer
from agents.asset_manager import AssetManager
from agents.quant_analyst import QuantAnalyst
from agents.sentiment_analyst import SentimentAnalyst
from agents.ml_engineer import MLEngineer
from agents.risk_manager import RiskManager
from agents.quant_trader import QuantTrader

def get_active_strategy():
    """Returns the entire JSON object from active_policy.json."""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'active_policy.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception:
        return {
            "strategy": "ema",
            "timeframe": "5m",
            "interval_seconds": 3600,
            "alpha_half_life_seconds": 300,
            "alpha_decay_veto_threshold": 0.5,
        }

def get_loop_interval(policy):
    """Dynamically extracts interval_seconds, defaulting to 1 hour (3600s) if missing."""
    return policy.get("interval_seconds", 3600)

def run_trading_cycle(agents, policy):
    strategy_name = policy.get("strategy", "ema")
    print(f"\n--- [Skanda] Starting Cycle | Strategy: {strategy_name} ---")

    # Re-read policy fresh at start of each cycle for hot-reload of all fields
    fresh_policy = get_active_strategy()

    # 1. Data Engineer fetches OHLCV sized for the active timeframe
    data_response = agents['data'].fetch_market_data()
    standard_payload = data_response.get("data", {})
    symbol = standard_payload.get("symbol", "BTCUSDT")

    # 1b. Asset Manager — lead–lag intelligence over the multi-coin panel
    by_sym = standard_payload.get("ohlcv_by_symbol") or {}
    standard_payload["asset_manager"] = agents["asset_manager"].identify_lead_lag(ohlcv_by_symbol=by_sym)

    # 2. Sentiment Analyst gets scores with DYNAMIC text input
    dynamic_text = f"Market action for {symbol} is showing interesting volume patterns on the {fresh_policy.get('timeframe')} chart. Traders are closely watching the resistance levels."
    sentiment_response = agents['sentiment'].act("analyze_sentiment", {"text": dynamic_text})
    sentiment_data = sentiment_response.get("data", {})
    sentiment_score = sentiment_data.get("sentiment_score", 0.0)

    # 3. Quant Analyst evaluates, extracting trade signal
    quant_payload = agents['quant'].evaluate_market(standard_payload)
    trade_proposal = quant_payload.get("data", {})
    trade_proposal["strategy_used"] = strategy_name
    trade_proposal["symbol"] = symbol
    trade_proposal["sentiment_score"] = sentiment_score

    # 4. ML Engineer provides probabilistic validation
    ml_features = {
        "quant_signal":    trade_proposal.get("signal_type", "HOLD"),
        "sentiment_score": sentiment_score,
        "active_strategy": strategy_name
    }
    ml_validation = agents['ml'].validate_signal(ml_features)
    ml_data = ml_validation.get("data", {})
    win_prob = ml_data.get("win_probability", 50.0)

    print(f"[Skanda] Strategy: {strategy_name} | Sentiment: {sentiment_score} | Dynamic Win Prob: {win_prob}%")

    # 5. Risk Manager evaluates proposal with ML context
    risk_evaluation = agents['risk'].evaluate_trade(trade_proposal, ml_data)
    risk_data = risk_evaluation.get("data", {})

    # 6. Handle Veto & Memory Alerts
    if risk_data.get("strike_alert", False):
        agents['proxy'].act("alert", f"Strategy '{risk_data.get('failed_strategy')}' has been vetoed 3+ times consecutively. Consider switching strategies.")

    if risk_data.get("status") == "vetoed":
        print(f"--- [Forward Test] Cycle Skipped: Trade Vetoed ({risk_data.get('reason')}) ---\n")
        return

    # 7. Quant Trader executes if approved
    agents['trader'].execute_trade(trade_proposal, standard_payload)
    print("--- [Forward Test] Cycle Complete ---\n")

def get_mode_name(interval):
    if interval < 900:
        return f"Scalper Mode ({interval}s)"
    else:
        return f"Swing Mode ({interval}s)"

def main():
    print("Initializing Forward Testing Environment...")
    asset_manager = AssetManager()
    agents = {
        'proxy': UserProxy(),
        'data': DataEngineer(),
        'asset_manager': asset_manager,
        'quant': QuantAnalyst(),
        'sentiment': SentimentAnalyst(),
        'ml': MLEngineer(),
        'risk': RiskManager(),
        'trader': QuantTrader()
    }
    
    current_policy = get_active_strategy()
    loop_interval = get_loop_interval(current_policy)
    
    mode_name = get_mode_name(loop_interval)
    strategy_name = current_policy.get('strategy', 'ema')
    print(f"Testing started: Strategy='{strategy_name}' | Mode={mode_name}")
    
    while True:
        latest_policy = get_active_strategy()
        latest_strategy_name = latest_policy.get('strategy', 'ema')
        
        # Check for policy updates (any field — strategy, timeframe, interval)
        if json.dumps(latest_policy, sort_keys=True) != json.dumps(current_policy, sort_keys=True):
            latest_strategy_name = latest_policy.get('strategy', 'ema')
            agents['proxy'].announce_strategy_change(latest_strategy_name)
            current_policy  = latest_policy
            strategy_name   = latest_strategy_name
            agents['quant'].load_active_strategy()

            loop_interval = get_loop_interval(current_policy)
            mode_name     = get_mode_name(loop_interval)
            tf            = current_policy.get('timeframe', '5m')
            print(f"Policy changed → Strategy={strategy_name} | Timeframe={tf} | Mode={mode_name}")
            
        try:
            run_trading_cycle(agents, current_policy)
            
            print(f"Cycle completed. Waiting {loop_interval} seconds for the next cycle...")
            time.sleep(loop_interval)
            
        except KeyboardInterrupt:
            print("\nForward testing stopped by user.")
            break
        except Exception as e:
            print(f"Error in testing cycle: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
