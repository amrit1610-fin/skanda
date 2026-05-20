import pandas as pd
import numpy as np

def generate_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    # 1. Core Indicators
    ema8 = df['close'].ewm(span=8, adjust=False).mean()
    ema30 = df['close'].ewm(span=30, adjust=False).mean()
    vol_sma = df['volume'].rolling(window=20).mean()
    
    # 2. Corrected ATR Calculation (Wilder's Smoothing approximated with EWM)
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean() 
    natr = (atr / df['close']) * 100
    
    # 3. Structural Filters
    ema_dist = ((ema8 - ema30).abs() / df['close']) * 100
    
    # Slope calculation: Is the 30 EMA actually moving? (Comparing current to 3 bars ago)
    ema30_slope = ((ema30 - ema30.shift(3)) / df['close']) * 100 
    min_slope_threshold = natr * 0.05 # Require slope to be at least 5% of NATR
    
    # Trend Definition (Price + EMAs + Slope)
    uptrend = (ema8 > ema30) & (ema30_slope > min_slope_threshold)
    downtrend = (ema8 < ema30) & (ema30_slope < -min_slope_threshold)
    
    # 4. Pullback & Rejection Logic
    # We want a touch of the 8 EMA, but ideally it shouldn't breach the 30 EMA (which invalidates the trend)
    long_pullback = (df['low'] <= ema8) & (df['low'] > ema30) & (df['close'] > ema8)
    short_pullback = (df['high'] >= ema8) & (df['high'] < ema30) & (df['close'] < ema8)
    
    # 5. Signal Generation
    buy_signal_bar = uptrend & long_pullback & (df['volume'] > vol_sma) & (ema_dist > (natr * 0.3))
    sell_signal_bar = downtrend & short_pullback & (df['volume'] > vol_sma) & (ema_dist > (natr * 0.3))
    
    # 6. Shift signals by 1 to represent executing on the Open of the *next* bar
    buy_cond = buy_signal_bar.shift(1).fillna(False)
    sell_cond = sell_signal_bar.shift(1).fillna(False)
    
    return buy_cond, sell_cond