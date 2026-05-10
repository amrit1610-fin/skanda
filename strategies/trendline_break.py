import pandas as pd
import numpy as np

def generate_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    # 1. Macro Trend Filter (Don't trade against the institutional tide)
    ema200 = df['close'].ewm(span=200, adjust=False).mean()
    
    # 2. Structural Range (Donchian Channel)
    # We shift this here so we are comparing today's price to YESTERDAY'S 20-day high
    rolling_high = df['high'].rolling(window=20).max().shift(1)
    rolling_low = df['low'].rolling(window=20).min().shift(1)
    
    # 3. Volatility & Volume Conviction Filters
    # True Range for accurate volatility
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean()
    
    vol_sma = df['volume'].rolling(window=20).mean()
    
    # Require the breakout to clear the level by at least 20% of ATR
    breakout_buffer = atr * 0.2 
    
    # 4. Breakout Logic 
    # Must clear the level + buffer, have above-average volume, and align with the 200 EMA
    long_breakout_bar = (
        (df['close'] > (rolling_high + breakout_buffer)) & 
        (df['volume'] > vol_sma) &
        (df['close'] > ema200)
    )
    
    short_breakout_bar = (
        (df['close'] < (rolling_low - breakout_buffer)) & 
        (df['volume'] > vol_sma) &
        (df['close'] < ema200)
    )
    
    # 5. Execution Reality: Shift to enter on the next bar's open
    buy_cond = long_breakout_bar.shift(1).fillna(False)
    sell_cond = short_breakout_bar.shift(1).fillna(False)
    
    return buy_cond, sell_cond