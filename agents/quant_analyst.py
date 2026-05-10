import json
import os
import time
import pandas as pd
from .base_agent import ReActAgent
from utils.math_engine import calculate_macd, calculate_rsi, calculate_vwap

PAIR_MEAN_REVERSION_STRATS = frozenset({"pairs_trading", "mean_reversion"})

# Regime IDs that indicate a bear/downtrend market (from MacroEconomist)
BEAR_REGIME_IDS = frozenset({2})  # regime_id == 2 → High Volatility / Bear Trend


class QuantAnalyst(ReActAgent):
    def __init__(self):
        super().__init__("QuantAnalyst")
        self._active_strategy_key = "ema"
        self.load_active_strategy()

    def load_active_strategy(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'active_policy.json')
        self.think(f"Reading active policy from {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                raw = config.get("strategy", "ema")
                strategy = str(raw).lower().strip().replace(" ", "_").replace("-", "_")
                if strategy in ("pairs_trading", "pairstrading"):
                    strategy = "pairs_trading"
                if strategy in ("mean_reversion", "meanreversion"):
                    strategy = "mean_reversion"
                self._active_strategy_key = strategy
                self.think(f"Active strategy determined as: {strategy}")
                
                strategy_map = {
                    "turtle": "turtle_system.md",
                    "connors": "connors_rsi.md",
                    "stat_arb": "stat_arb.md",
                }
                
                skill_filename = strategy_map.get(strategy, "turtle_system.md")
                skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'quant_analyst', skill_filename)
                
                # This will automatically trigger _parse_and_load_tool() from BaseAgent
                self.load_skills(skill_path)
                
        except Exception as e:
            self.think(f"Error loading strategy: {e}")
            self._active_strategy_key = getattr(self, "_active_strategy_key", "ema")

    def _apply_confluence_filter(self, signal_type: str, ohlcv_data: pd.DataFrame) -> str:
        """
        Applies a multi-indicator confluence gate on top of raw strategy signals.
        BUY requires: close > VWAP AND MACD > Signal AND RSI < 70
        SELL requires: close < VWAP AND MACD < Signal AND RSI > 30
        Returns the filtered signal ('buy', 'sell', or 'hold').
        """
        if signal_type not in ('buy', 'sell'):
            return signal_type

        try:
            if ohlcv_data is None or len(ohlcv_data) < 30:
                return signal_type  # Not enough data to apply confluence, pass through

            close = ohlcv_data['close']
            current_close = close.iloc[-1]

            # VWAP
            vwap = calculate_vwap(ohlcv_data).iloc[-1]

            # MACD
            macd_line, signal_line, _ = calculate_macd(close)
            current_macd = macd_line.iloc[-1]
            current_signal = signal_line.iloc[-1]

            # RSI
            rsi = calculate_rsi(close).iloc[-1]

            if signal_type == 'buy':
                confluence_met = (
                    current_close > vwap
                    and current_macd > current_signal
                    and rsi < 70
                )
                if not confluence_met:
                    self.think(
                        f"Confluence FAILED for BUY: close={current_close:.2f}, VWAP={vwap:.2f}, "
                        f"MACD={current_macd:.4f}, Signal={current_signal:.4f}, RSI={rsi:.1f} → HOLD"
                    )
                    return 'hold'

            elif signal_type == 'sell':
                confluence_met = (
                    current_close < vwap
                    and current_macd < current_signal
                    and rsi > 30
                )
                if not confluence_met:
                    self.think(
                        f"Confluence FAILED for SELL: close={current_close:.2f}, VWAP={vwap:.2f}, "
                        f"MACD={current_macd:.4f}, Signal={current_signal:.4f}, RSI={rsi:.1f} → HOLD"
                    )
                    return 'hold'

            self.think(f"Confluence PASSED for {signal_type.upper()}.")
        except Exception as e:
            self.think(f"Confluence filter error (passing through): {e}")

        return signal_type

    def evaluate_market(self, payload):
        self.think("Evaluating market conditions against Strategy Logic...")
        
        # --- Dynamically load strategy .md and append to system prompt ---
        strategy_map = {
            "turtle": "turtle_system",
            "connors": "connors_rsi",
            "stat_arb": "stat_arb"
        }
        strategy_module_name = strategy_map.get(self._active_strategy_key, "turtle_system")
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'quant_analyst', f"{strategy_module_name}.md")
        
        if not hasattr(self, '_original_system_prompt'):
            self._original_system_prompt = getattr(self, 'system_prompt', '')
            
        try:
            # 1. Read base persona from skills
            with open(skill_path, "r", encoding="utf-8") as f:
                base_persona = f.read()
                
            # 2. Dynamically import mathematical prompt from python module
            import importlib
            mod = importlib.import_module(f"strategies.{strategy_module_name}")
            ai_prompt = getattr(mod, "AI_PROMPT", "No specific mathematical prompt provided.")
            
            # 3. Concatenate
            self.system_prompt = self._original_system_prompt + f"\n\n--- BASE PERSONA ---\n{base_persona}\n\n--- MATHEMATICAL PARAMETERS ---\n{ai_prompt}"
            self.think(f"Successfully loaded {strategy_module_name}.md and AI_PROMPT.")
        except Exception as e:
            self.think(f"Error loading strategy logic: {e}")
        # -----------------------------------------------------------------

        ohlcv_data = payload.get("ohlcv_data")
        macro_news = payload.get("macro_news", {})
        sym = payload.get("symbol", "BTCUSDT")

        # ── KING FILTER: BTC Regime Gate for Altcoins ────────────────────────
        # If the symbol is NOT BTC, check the macro regime.
        # In a bear market, all altcoin signals are suppressed to HOLD.
        is_btc = str(sym).upper().replace("/", "").replace("-", "") in ("BTCUSDT", "BTC")
        if not is_btc:
            regime_id = macro_news.get("regime_id") if isinstance(macro_news, dict) else None
            if regime_id in BEAR_REGIME_IDS:
                self.think(
                    f"KING FILTER: Bear market regime detected (regime_id={regime_id}). "
                    f"Suppressing altcoin {sym} signal → HOLD."
                )
                return self.act("evaluate_market", {
                    "strategy_used": self._active_strategy_key,
                    "symbol": sym,
                    "signal_type": "hold",
                    "signal_timestamp": time.time(),
                    "win_probability": 0.0,
                    "sentiment_score": 0.8,
                    "analysis_details": {"signal": "HOLD", "values": {}},
                    "macro_context": macro_news,
                    "asset_manager": payload.get("asset_manager"),
                    "signal_from_cointegration": False,
                })
        # ─────────────────────────────────────────────────────────────────────

        # Enforce Tool Execution, passing ONLY the OHLCV data to the mathematical tool
        analysis_result = self.enforce_tool_execution(ohlcv_data)
        
        if analysis_result is None:
            self.think("No valid tool execution result. Defaulting to HOLD.")
            analysis_result = {"signal": "HOLD", "values": {}}
            
        signal_type = analysis_result.get("signal", "HOLD").lower()
        win_prob = 0.6 if signal_type in ['buy', 'sell'] else 0.0

        pair_z_score = None
        pair_p_value = None
        pair_leg_x = None
        pair_hedge_ratio = None
        signal_from_cointegration = False

        am = payload.get("asset_manager") or {}
        by_y = am.get("cointegration_by_symbol_y") or {}
        pair_row = by_y.get(sym) or by_y.get(str(sym).upper())

        if self._active_strategy_key in PAIR_MEAN_REVERSION_STRATS and pair_row and pair_row.get("is_cointegrated"):
            z = pair_row.get("current_z_score")
            pair_p_value = pair_row.get("p_value")
            pair_leg_x = pair_row.get("asset_x")
            pair_hedge_ratio = pair_row.get("hedge_ratio")
            if z is not None:
                pair_z_score = float(z)
                if z > 2.0:
                    signal_type = "sell"
                    signal_from_cointegration = True
                    self.think(f"Cointegration: z={z:.3f} > 2 → SHORT {sym} vs {pair_leg_x}")
                elif z < -2.0:
                    signal_type = "buy"
                    signal_from_cointegration = True
                    self.think(f"Cointegration: z={z:.3f} < -2 → BUY {sym} vs {pair_leg_x}")
                else:
                    signal_type = "hold"
                    self.think(f"Cointegration: z={z:.3f} in band — HOLD (mean-reversion idle)")
            else:
                signal_type = "hold"
        elif self._active_strategy_key in PAIR_MEAN_REVERSION_STRATS:
            signal_type = "hold"
            self.think("Pairs / mean-reversion mode: no cointegrated pair for active symbol — HOLD")

        # ── CONFLUENCE FILTER (non-cointegration strategies only) ─────────────
        if not signal_from_cointegration and isinstance(ohlcv_data, pd.DataFrame):
            signal_type = self._apply_confluence_filter(signal_type, ohlcv_data)
        # ─────────────────────────────────────────────────────────────────────

        win_prob = 0.6 if signal_type in ['buy', 'sell'] else 0.0

        trade_proposal = {
            "strategy_used": self._active_strategy_key,
            "symbol": sym,
            "signal_type": signal_type,
            "signal_timestamp": time.time(),
            "win_probability": win_prob,
            "sentiment_score": 0.8,
            "analysis_details": analysis_result,
            "macro_context": macro_news,
            "asset_manager": payload.get("asset_manager"),
            "signal_from_cointegration": signal_from_cointegration,
            "pair_z_score": pair_z_score,
            "pair_p_value": pair_p_value,
            "pair_leg_y": sym,
            "pair_leg_x": pair_leg_x,
            "pair_hedge_ratio": pair_hedge_ratio,
        }
        
        return self.act("evaluate_market", trade_proposal)


