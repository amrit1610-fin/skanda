import json
import os
from .base_agent import ReActAgent

class QuantAnalyst(ReActAgent):
    def __init__(self):
        super().__init__("QuantAnalyst")
        self.load_active_strategy()

    def load_active_strategy(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'active_policy.json')
        self.think(f"Reading active policy from {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                strategy = config.get("strategy", "ema")
                self.think(f"Active strategy determined as: {strategy}")
                
                strategy_map = {
                    "ema": "ema_crossover.md",
                    "bollinger": "bollinger_bands.md",
                    "trendline": "trendline_breakout.md",
                    "rsi": "rsi_scalper.md",
                    "macd": "macd_momentum.md"
                }
                
                skill_filename = strategy_map.get(strategy, "ema_crossover.md")
                skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'quant_analyst', skill_filename)
                
                # This will automatically trigger _parse_and_load_tool() from BaseAgent
                self.load_skills(skill_path)
                
        except Exception as e:
            self.think(f"Error loading strategy: {e}")

    def evaluate_market(self, payload):
        self.think("Evaluating market conditions against Strategy Logic...")
        
        # The payload is now the standard JSON handshake from DataEngineer
        ohlcv_data = payload.get("ohlcv_data")
        macro_news = payload.get("macro_news", {})
        
        # Enforce Tool Execution, specifically passing ONLY the OHLCV data to the mathematical tool
        analysis_result = self.enforce_tool_execution(ohlcv_data)
        
        if analysis_result is None:
            self.think("No valid tool execution result. Defaulting to HOLD.")
            analysis_result = {"signal": "HOLD", "values": {}}
            
        signal_type = analysis_result.get("signal", "HOLD").lower()
        win_prob = 0.6 if signal_type in ['buy', 'sell'] else 0.0

        sym = payload.get("symbol", "BTCUSDT")

        trade_proposal = {
            "strategy_used": "unknown",
            "symbol": sym,
            "signal_type": signal_type,
            "win_probability": win_prob,
            "sentiment_score": 0.8,
            "analysis_details": analysis_result,
            "macro_context": macro_news,
            "asset_manager": payload.get("asset_manager"),
        }
        
        return self.act("evaluate_market", trade_proposal)
