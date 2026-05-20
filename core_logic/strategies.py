import pandas as pd
import numpy as np

def generate_ema_8_30_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Strategy 1: 8/30 EMA Momentum with Slope & ATR Filters"""
    df = df.copy()
    ema8 = df['close'].ewm(span=8, adjust=False).mean()
    ema30 = df['close'].ewm(span=30, adjust=False).mean()
    vol_sma = df['volume'].rolling(window=20).mean()
    
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean() 
    natr = (atr / df['close']) * 100
    
    ema_dist = ((ema8 - ema30).abs() / df['close']) * 100
    ema30_slope = ((ema30 - ema30.shift(3)) / df['close']) * 100 
    min_slope_threshold = natr * 0.05 
    
    uptrend = (ema8 > ema30) & (ema30_slope > min_slope_threshold)
    downtrend = (ema8 < ema30) & (ema30_slope < -min_slope_threshold)
    
    long_pullback = (df['low'] <= ema8) & (df['low'] > ema30) & (df['close'] > ema8)
    short_pullback = (df['high'] >= ema8) & (df['high'] < ema30) & (df['close'] < ema8)
    
    buy_signal_bar = uptrend & long_pullback & (df['volume'] > vol_sma) & (ema_dist > (natr * 0.3))
    sell_signal_bar = downtrend & short_pullback & (df['volume'] > vol_sma) & (ema_dist > (natr * 0.3))
    
    # Executing on the Open of the *next* bar
    return buy_signal_bar.shift(1).fillna(False).astype(bool), sell_signal_bar.shift(1).fillna(False).astype(bool)


def generate_ema_9_15_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Strategy 2: 9/15 EMA Scalping with Candlestick Snapback"""
    df = df.copy()
    ema9 = df['close'].ewm(span=9, adjust=False).mean()
    ema15 = df['close'].ewm(span=15, adjust=False).mean()
    ema50 = df['close'].ewm(span=50, adjust=False).mean()
    
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean()
    natr = (atr / df['close']) * 100
    
    ribbon_dist = ((ema9 - ema15).abs() / df['close']) * 100
    is_separated = ribbon_dist > (natr * 0.2)
    
    ema15_roc = ((ema15 - ema15.shift(5)) / df['close']) * 100 
    min_slope = natr * 0.1 
    
    strong_up_slope = is_separated & (ema15_roc > min_slope) & (ema15 > ema50)
    strong_down_slope = is_separated & (ema15_roc < -min_slope) & (ema15 < ema50)
    
    long_entry = (df['low'] <= ema9) & (df['close'] > ema9) & (df['close'] > df['open'])
    short_entry = (df['high'] >= ema9) & (df['close'] < ema9) & (df['close'] < df['open'])
    
    buy_signal = strong_up_slope & long_entry & (df['close'] > ema50)
    sell_signal = strong_down_slope & short_entry & (df['close'] < ema50)
    
    return buy_signal.shift(1).fillna(False).astype(bool), sell_signal.shift(1).fillna(False).astype(bool)


def generate_trendline_break_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Strategy 3: Multi-TF Trendline Break (Donchian / 200 EMA)"""
    df = df.copy()
    ema200 = df['close'].ewm(span=200, adjust=False).mean()
    
    rolling_high = df['high'].rolling(window=20).max().shift(1)
    rolling_low = df['low'].rolling(window=20).min().shift(1)
    
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean()
    
    vol_sma = df['volume'].rolling(window=20).mean()
    breakout_buffer = atr * 0.2 
    
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
    
    return long_breakout_bar.shift(1).fillna(False).astype(bool), short_breakout_bar.shift(1).fillna(False).astype(bool)

def get_signal_for_strategy(df: pd.DataFrame, strategy_name: str) -> str:
    """
    Router function used by the Universal Engine to extract the current signal
    for the latest candle based on the active policy.
    Returns: "BUY", "SELL", or "HOLD"
    """
    if df.empty: return "HOLD"
    
    # Map the string name from active_policy.json to the specific function
    strategy_map = {
        "ema_8_30": generate_ema_8_30_signals,
        "ema_9_15": generate_ema_9_15_signals,
        "trendline_break": generate_trendline_break_signals
    }
    
    # Default to 8/30 if strategy is unknown
    func = strategy_map.get(strategy_name, generate_ema_8_30_signals)
    
    buy_series, sell_series = func(df)
    
    # Look at the very last row of the dataframe (the current actionable bar)
    is_buy = buy_series.iloc[-1]
    is_sell = sell_series.iloc[-1]
    
    if is_buy: return "BUY"
    if is_sell: return "SELL"
    return "HOLD"