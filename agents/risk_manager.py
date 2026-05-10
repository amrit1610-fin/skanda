import os
import json
import time
import torch
from datetime import datetime
from mem0 import Memory
from .base_agent import ReActAgent
from utils.alpha_decay import calculate_alpha_decay

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

    def _load_alpha_policy(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'active_policy.json')
        try:
            with open(config_path, 'r') as f:
                c = json.load(f)
            half_life = float(c.get("alpha_half_life_seconds", 300))
            if half_life <= 0:
                half_life = 300.0
            threshold = float(c.get("alpha_decay_veto_threshold", 0.5))
            return half_life, threshold
        except Exception:
            return 300.0, 0.5

    def _side_from_signal(self, signal_type: str) -> str:
        s = (signal_type or "HOLD").upper()
        if s == "BUY":
            return "LONG"
        if s == "SELL":
            return "SHORT"
        return "FLAT"

    def calculate_trade_brackets(
        self,
        side: str,
        entry_price: float,
        sl_pct: float = 0.02,
        tp_pct: float = 0.06,
        atr: float = None,
    ) -> dict:
        """
        Calculates bracketed stop-loss and take-profit prices.
        If atr is provided, uses volatility-based sizing (1.5x ATR for SL, 3.0x ATR for TP).
        Otherwise, falls back to percentage-based method.
        """
        side = str(side).lower()

        if atr is not None and atr > 0:
            # ATR-based volatility sizing (institutional grade)
            sl_dist = 1.5 * atr
            tp_dist = 3.0 * atr
            if side in ('buy', 'long'):
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tp_dist
            elif side in ('sell', 'short'):
                sl_price = entry_price + sl_dist
                tp_price = entry_price - tp_dist
            else:
                sl_price = entry_price
                tp_price = entry_price
        else:
            # Fallback: percentage-based method
            if side in ('buy', 'long'):
                sl_price = entry_price * (1 - sl_pct)
                tp_price = entry_price * (1 + tp_pct)
            elif side in ('sell', 'short'):
                sl_price = entry_price * (1 + sl_pct)
                tp_price = entry_price * (1 - tp_pct)
            else:
                sl_price = entry_price
                tp_price = entry_price

        return {
            "stop_loss": round(sl_price, 4),
            "take_profit": round(tp_price, 4),
        }


    def log_trade_event(
        self,
        strategy_used,
        signal_type,
        win_probability,
        sentiment_score,
        status,
        reason="",
        symbol="BTCUSDT",
        decay_factor=None,
        pair_z_score=None,
        pair_p_value=None,
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
        if decay_factor is not None:
            event["decay_factor"] = float(decay_factor)
        if pair_z_score is not None:
            event["pair_z_score"] = float(pair_z_score)
        if pair_p_value is not None:
            try:
                event["pair_p_value"] = float(pair_p_value)
            except (TypeError, ValueError):
                event["pair_p_value"] = pair_p_value
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
        
        half_life, decay_threshold = self._load_alpha_policy()
        decay_factor = 1.0
        if signal_type in ("BUY", "SELL"):
            sig_ts = float(trade_proposal.get("signal_timestamp", time.time()))
            decay_factor, _ = calculate_alpha_decay(sig_ts, time.time(), half_life)
            decay_factor = float(decay_factor)
        trade_proposal["decay_factor"] = decay_factor

        status = "approved"
        reason = "Passed all risk checks"
        strike_alert = False
        alpha_veto = False

        if signal_type in ("BUY", "SELL") and decay_factor < decay_threshold:
            alpha_veto = True
            status = "vetoed"
            reason = "Alpha Expired - Signal Stale"

        if not alpha_veto:
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
        
        pz = trade_proposal.get("pair_z_score")
        pp = trade_proposal.get("pair_p_value")
        if not trade_proposal.get("signal_from_cointegration"):
            pz, pp = None, None

        self.log_trade_event(
            strategy_used=strategy_used,
            signal_type=signal_type,
            win_probability=win_prob,
            sentiment_score=sentiment_score,
            status=status,
            reason=reason,
            symbol=sym,
            decay_factor=decay_factor,
            pair_z_score=pz,
            pair_p_value=pp,
        )
        
        return self.act("evaluate_risk", {
            "status": status, 
            "reason": reason, 
            "strike_alert": strike_alert,
            "failed_strategy": strategy_used,
            "decay_factor": decay_factor,
        })
