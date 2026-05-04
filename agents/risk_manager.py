import os
import json
import torch
from datetime import datetime
from mem0 import Memory
from .base_agent import ReActAgent

class RiskManager(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'risk_manager', 'system_prompt.md')
        super().__init__("RiskManager", skill_path)
        self.log_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'trade_history.json')
        self._ensure_log_file()
        
        # Initialize Mem0 with local HuggingFace embeddings
        self.think("Initializing Mem0 memory layer with local huggingface embeddings...")
        
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "path": os.path.join(os.path.dirname(__file__), '..', 'logs', 'mem0_db')
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": "sentence-transformers/all-MiniLM-L6-v2"
                }
            }
        }
        
        try:
            self.memory = Memory.from_config(config)
            self.think("Mem0 initialized successfully.")
        except Exception as e:
            self.think(f"Warning: Mem0 initialization failed: {e}")
            self.memory = None

    def _ensure_log_file(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def _side_from_signal(self, signal_type: str) -> str:
        s = (signal_type or "HOLD").upper()
        if s == "BUY":
            return "LONG"
        if s == "SELL":
            return "SHORT"
        return "FLAT"

    def log_trade_event(
        self,
        strategy_used,
        signal_type,
        win_probability,
        sentiment_score,
        status,
        reason="",
        symbol="BTCUSDT",
    ):
        self.think(f"Logging risk management decision: status={status}")
        try:
            with open(self.log_file, 'r') as f:
                history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = []

        st = (signal_type or "HOLD").upper()
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "strategy_used": strategy_used,
            "signal_type": st,
            "side": self._side_from_signal(st),
            "win_probability": win_probability,
            "sentiment_score": sentiment_score,
            "status": status,
            "reason": reason,
        }
        history.append(event)

        with open(self.log_file, 'w') as f:
            json.dump(history, f, indent=4)

    def evaluate_trade(self, trade_proposal, ml_validation):
        self.think(f"Evaluating trade proposal and ML validation...")
        
        strategy_used = trade_proposal.get("strategy_used", "unknown")
        signal_type = trade_proposal.get("signal_type", "HOLD").upper()
        sentiment_score = trade_proposal.get("sentiment_score", 0)
        sym = trade_proposal.get("symbol", "BTCUSDT")
        
        # Get ML probabilities
        win_prob = ml_validation.get("win_probability", 0)
        ml_action = ml_validation.get("recommended_action", "HOLD").upper()
        
        status = "approved"
        reason = "Passed all risk checks"
        strike_alert = False
        
        # Decision Logic: Veto if ML probability < 55% or Signal is HOLD
        if win_prob < 55.0 or ml_action == "HOLD" or signal_type == "HOLD":
            status = "vetoed"
            reason = f"ML Win Probability is {win_prob}% (< 55%)" if win_prob < 55.0 else "Signal is HOLD"
            
            # Store in Mem0
            self.think(f"Vetoing trade. Storing failure memory for strategy: {strategy_used}")
            memory_text = f"Strategy '{strategy_used}' was vetoed due to {reason}."
            
            if self.memory:
                try:
                    self.memory.add(memory_text, user_id="risk_manager")
                    
                    # Search recent memories
                    recent_memories = self.memory.search(f"Strategy '{strategy_used}' was vetoed", user_id="risk_manager", limit=5)
                    veto_count = sum(1 for m in recent_memories if strategy_used in m.get('memory', ''))
                    
                    if veto_count >= 3:
                        self.think(f"ALERT: Strategy {strategy_used} has failed {veto_count} times recently.")
                        strike_alert = True
                except Exception as e:
                    self.think(f"Error interacting with Mem0: {e}")
        
        self.log_trade_event(
            strategy_used=strategy_used,
            signal_type=signal_type,
            win_probability=win_prob,
            sentiment_score=sentiment_score,
            status=status,
            reason=reason,
            symbol=sym,
        )
        
        return self.act("evaluate_risk", {
            "status": status, 
            "reason": reason, 
            "strike_alert": strike_alert,
            "failed_strategy": strategy_used
        })
