import pandas as pd
import numpy as np

def generate_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    # 1. Core EMA Ribbon
    ema9 = df['close'].ewm(span=9, adjust=False).mean()
    ema15 = df['close'].ewm(span=15, adjust=False).mean()
    ema50 = df['close'].ewm(span=50, adjust=False).mean()
    
    # 2. Proper Volatility Calculation (14-period True Range)
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean()
    
    # 3. Slope & Separation Mechanics
    # Separation: The ribbon must be fanned out (distance proxy)
    ribbon_dist = (ema9 - ema15).abs()
    is_separated = ribbon_dist > (atr * 0.2)
    
    # True Slope: The 15 EMA must be moving directionally over a 5-bar window
    ema15_roc = ema15.diff(5) 
    min_slope = atr * 0.1 # Slope must exceed 10% of ATR over 5 bars
    
    strong_up_slope = is_separated & (ema15_roc > min_slope) & (ema15 > ema50)
    strong_down_slope = is_separated & (ema15_roc < -min_slope) & (ema15 < ema50)
    
    # 4. Candlestick Rejection Logic (The "Snapback")
    # Long: Drops to touch the 9 EMA, but bulls immediately push it to close green AND back above the 9 EMA.
    long_entry = (df['low'] <= ema9) & (df['close'] > ema9) & (df['close'] > df['open'])
    
    # Short: Rallies to touch the 9 EMA, but bears push it to close red AND back below the 9 EMA.
    short_entry = (df['high'] >= ema9) & (df['close'] < ema9) & (df['close'] < df['open'])
    
    # 5. Signal Assembly (Ensuring 50 EMA regime is respected)
    buy_signal = strong_up_slope & long_entry & (df['close'] > ema50)
    sell_signal = strong_down_slope & short_entry & (df['close'] < ema50)
    
    # 6. Execution Reality: Shift by 1 to execute on the open of the next bar
    buy_cond = buy_signal.shift(1).fillna(False)
    sell_cond = sell_signal.shift(1).fillna(False)
    
    return buy_cond, sell_cond