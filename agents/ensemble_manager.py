import pandas as pd
import numpy as np
import joblib
import os
import json
from strategies import ema_8_30, ema_9_15, trendline_break
from utils.llm_bridge import get_cio_decision

class MacroState:
    def __init__(self, state_file="macro_state.json"):
        self.state_file = state_file
        self.bias = "Neutral"
        self.risk_score = 5

    def _load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.bias = data.get("bias", "Neutral")
                    self.risk_score = data.get("risk_score", 5)
        except:
            pass

    def get_current_bias(self):
        self._load_state()
        return self.bias

    def get_risk_score(self):
        self._load_state()
        return self.risk_score

class StrategyEnsemble:
    def __init__(self, model_path="xgboost_btc_model.pkl"):
        if not os.path.exists(model_path):
            alt_path = os.path.join("ml_pipeline", model_path)
            if os.path.exists(alt_path):
                model_path = alt_path
                
        try:
            self.model = joblib.load(model_path)
        except Exception as e:
            print(f"Warning: Could not load model from {model_path}. Using fallback logic. {e}")
            self.model = None
            
        self.macro_state = MacroState()

    def predict_regime(self, df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
        if self.model is None:
            # Fallback: assume trend
            return pd.Series(1, index=df.index), pd.DataFrame()

        df_feat = pd.DataFrame(index=df.index)
        
        close = df['close'] if 'close' in df else df['Close']
        high = df['high'] if 'high' in df else df['High']
        low = df['low'] if 'low' in df else df['Low']
        open_col = df['open'] if 'open' in df else df['Open']
        vol = df['volume'] if 'volume' in df else df['Volume']

        # 1. RSI_14
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_feat['RSI_14'] = 100 - (100 / (1 + rs))

        # 2. Log_Ret_5
        df_feat['Log_Ret_5'] = np.log(close / close.shift(5))

        # 3. Tail_Ratio
        candle_range = high - low
        body_size = (close - open_col).abs()
        df_feat['Tail_Ratio'] = (candle_range - body_size) / (candle_range + 1e-9)

        # 4. Vol_ZScore
        vol_mean = vol.rolling(20).mean()
        vol_std = vol.rolling(20).std()
        df_feat['Vol_ZScore'] = (vol - vol_mean) / (vol_std + 1e-9)

        # 5. BB_Width
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        df_feat['BB_Width'] = (std20 * 4) / sma20 * 100

        features = ['RSI_14', 'Log_Ret_5', 'Tail_Ratio', 'Vol_ZScore', 'BB_Width']
        X = df_feat[features]
        X = X.fillna(0)
        
        preds = self.model.predict(X)
        return pd.Series(preds, index=df.index), df_feat

    def get_ensemble_signals(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        regime_preds, df_feat = self.predict_regime(df)
        
        buy_8_30, sell_8_30 = ema_8_30.generate_signals(df)
        buy_9_15, sell_9_15 = ema_9_15.generate_signals(df)
        buy_tb, sell_tb = trendline_break.generate_signals(df)
        
        # Binary ML model: 1 = Trend, 0 = Chop
        is_trend = (regime_preds == 1)
        is_chop = (regime_preds == 0)
        
        # MTF Resampling: "Base Pulse" Logic for Trend Filter
        if len(df) >= 2:
            try:
                ts = df['timestamp'] if 'timestamp' in df else pd.Series(df.index)
                current_bar_mins = (pd.to_datetime(ts.iloc[1]) - pd.to_datetime(ts.iloc[0])).total_seconds() / 60.0
            except:
                current_bar_mins = 60.0
        else:
            current_bar_mins = 60.0
            
        if current_bar_mins <= 0:
            current_bar_mins = 60.0
            
        target_lookback_mins = 240
        lookback = int(target_lookback_mins / current_bar_mins)
        if lookback < 1: lookback = 1
        
        macro_ema = df['close'].ewm(span=lookback, adjust=False).mean()
        macro_uptrend = df['close'] > macro_ema
        macro_downtrend = df['close'] < macro_ema
        
        # Calculate Volatility Spike for Scalper (using NATR)
        high_low = df['high'] - df['low']
        high_prev_close = (df['high'] - df['close'].shift(1)).abs()
        low_prev_close = (df['low'] - df['close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        atr = true_range.ewm(alpha=1/14, adjust=False).mean()
        natr = (atr / df['close']) * 100
        avg_natr = natr.rolling(window=50).mean()
        volatility_spike = natr > avg_natr
        
        # Hybrid Loop: Caching LLM calls every 4 hours
        active_strategy_series = pd.Series("ema_8_30", index=df.index)
        last_llm_time = None
        current_strategy = "ema_8_30"
        
        ts = df['timestamp'] if 'timestamp' in df else pd.Series(df.index)
        
        for i in range(len(df)):
            try:
                current_time = pd.to_datetime(ts.iloc[i])
                time_diff = (current_time - last_llm_time).total_seconds() if last_llm_time is not None else float('inf')
            except:
                time_diff = float('inf')
                current_time = None
                
                current_macro_bias = self.macro_state.get_current_bias()
                current_regime = int(regime_preds.iloc[i]) if not regime_preds.empty else 1
                print(f"DEBUG: Macro: {current_macro_bias}, Regime: {current_regime}")
                
                # LLM Call
                market_data = {
                    "xgboost_regime": current_regime,
                    "macro_economist_bias": current_macro_bias,
                    "macro_risk_level": self.macro_state.get_risk_score(),
                    "rsi": float(df_feat['RSI_14'].iloc[i]) if not df_feat.empty else 50.0,
                    "volatility_natr": float(natr.iloc[i]),
                    "is_volatility_spike": bool(volatility_spike.iloc[i]),
                    "macro_trend": "Bullish" if macro_uptrend.iloc[i] else ("Bearish" if macro_downtrend.iloc[i] else "Flat")
                }
                decision = get_cio_decision(market_data)
                current_strategy = decision.get("selected_strategy", "ema_8_30")
                
                if current_time is not None:
                    last_llm_time = current_time
                    
            active_strategy_series.iloc[i] = current_strategy
            
        # Strategy Gating by Resolution
        is_8_30 = (active_strategy_series == "ema_8_30")
        is_9_15 = (active_strategy_series == "ema_9_15")
        is_tb = (active_strategy_series == "trendline_break")
        
        current_macro_bias = self.macro_state.get_current_bias()
        
        # Hard Filter: If macro is Bearish, block all longs, but explicitly allow shorts
        buy_8_30_filtered = buy_8_30 & (current_macro_bias != "Bearish")
        buy_9_15_filtered = buy_9_15 & (current_macro_bias != "Bearish")
        buy_tb_filtered   = buy_tb   & (current_macro_bias != "Bearish")
        
        final_buy = (is_8_30 & buy_8_30_filtered & macro_uptrend) | (is_9_15 & buy_9_15_filtered & volatility_spike) | (is_tb & buy_tb_filtered & macro_uptrend)
        final_sell = (is_8_30 & sell_8_30 & macro_downtrend) | (is_9_15 & sell_9_15 & volatility_spike) | (is_tb & sell_tb & macro_downtrend)
        
        # Dynamic Stop Loss (The "Bleed" Protector)
        df['sl_override'] = np.where(is_9_15, 1.5, 2.0)
        df['tp_override'] = np.where(is_9_15, 3.0, 4.0)
        
        return final_buy, final_sell
