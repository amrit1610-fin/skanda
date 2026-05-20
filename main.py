import time
import json
import os
from datetime import datetime, timezone
from engine import run_trading_cycle
from agents.data_engineer import DataEngineer
from agents.quant_trader import QuantTrader
from agents.risk_manager import RiskManager
from agents.sentiment_analyst import SentimentAnalyst
from agents.macro_economist import MacroEconomist

def get_interval_seconds():
    """Reads the active policy to know how long to sleep between cycles."""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'active_policy.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f).get("interval_seconds", 300) # Default 5 mins
    except Exception:
        return 300

def main():
    print("🚀 Booting Skanda Autonomous Trading Bot...")
    
    # 1. Initialize all agents once
    agents = {
        'data': DataEngineer(),
        'trader': QuantTrader(),
        'risk': RiskManager(),
        'sentiment': SentimentAnalyst(),
        'economist': MacroEconomist()
    }
    
    print("✅ Agents initialized. Starting continuous trading loop.")

    # 2. The Immortal Loop
    while True:
        try:
            print(f"\n--- 🔄 Starting Trading Cycle at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} ---")
            
            # Fire the engine! This fetches data, updates the MTF radar, and trades.
            run_trading_cycle(agents)
            
            # Wait for the next candle
            sleep_time = get_interval_seconds()
            print(f"💤 Cycle complete. Sleeping for {sleep_time} seconds...")
            time.sleep(sleep_time)
            
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped manually by user.")
            break
        except Exception as e:
            print(f"⚠️ Critical error in main loop: {e}")
            print("Restarting cycle in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    main()