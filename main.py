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
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'active_policy.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f).get("strategy", "ema")
    except Exception:
        return "ema"

def run_trading_cycle(agents):
    print(f"\n--- Starting Trading Cycle at {datetime.now()} ---")
    
    # 1. Data Engineer fetches the standard JSON payload
    data_response = agents['data'].fetch_market_data()
    standard_payload = data_response.get("data", {})

    # 1b. Asset Manager — lead–lag intelligence over the multi-coin panel
    by_sym = standard_payload.get("ohlcv_by_symbol") or {}
    standard_payload["asset_manager"] = agents["asset_manager"].identify_lead_lag(ohlcv_by_symbol=by_sym)

    # 2. Sentiment Analyst gets scores
    sentiment_payload = agents['sentiment'].act("analyze_sentiment", standard_payload)
    
    # 3. Quant Analyst evaluates, extracting trade signal
    quant_payload = agents['quant'].evaluate_market(standard_payload)
    trade_proposal = quant_payload.get("data", {})
    trade_proposal["strategy_used"] = get_active_strategy()
    trade_proposal["symbol"] = standard_payload.get("symbol", trade_proposal.get("symbol", "BTCUSDT"))
    
    # 4. ML Engineer provides probabilistic validation
    ml_features = {
        "quant_signal": trade_proposal.get("signal_type", "HOLD"),
        "sentiment_score": trade_proposal.get("sentiment_score", 0.0)
    }
    ml_validation = agents['ml'].validate_signal(ml_features)
    ml_data = ml_validation.get("data", {})
    
    # 5. Risk Manager evaluates proposal with ML context
    risk_evaluation = agents['risk'].evaluate_trade(trade_proposal, ml_data)
    risk_data = risk_evaluation.get("data", {})
    
    # 6. Handle Veto & Memory Alerts
    if risk_data.get("strike_alert", False):
        agents['proxy'].act("alert", f"Strategy '{risk_data.get('failed_strategy')}' has been vetoed 3+ times consecutively. Consider switching strategies.")
        
    if risk_data.get("status") == "vetoed":
        print(f"--- Cycle Skipped: Trade Vetoed ({risk_data.get('reason')}) ---\n")
        return
    
    # 7. Quant Trader executes if approved
    agents['trader'].execute_trade(trade_proposal, standard_payload)
    print("--- Cycle Complete ---\n")

def main():
    print("Initializing AI Trading Agents...")
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
    
    current_strategy = get_active_strategy()
    print(f"System started with strategy: {current_strategy}")
    
    while True:
        latest_strategy = get_active_strategy()
        if latest_strategy != current_strategy:
            agents['proxy'].announce_strategy_change(latest_strategy)
            current_strategy = latest_strategy
            agents['quant'].load_active_strategy()
            
        try:
            run_trading_cycle(agents)
            
            print("Cycle completed. Waiting 60 minutes for the next cycle...")
            time.sleep(3600)
            
        except KeyboardInterrupt:
            print("\nTrading loop stopped by user.")
            break
        except Exception as e:
            print(f"Error in trading cycle: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
