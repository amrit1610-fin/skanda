import pandas as pd
import numpy as np

def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """Return series.ewm(span=span, adjust=False).mean()."""
    return series.ewm(span=span, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Wilder's RSI.
    Get the diff(). Separate gains and losses.
    Calculate the Exponential Moving Average (using ewm(alpha=1/period, adjust=False).mean())
    for both gains and absolute losses.
    Return 100 - (100 / (1 + (gains / losses))).
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    
    # Wilder's smoothing
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    # Avoid division by zero
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    Calculate fast EMA, slow EMA, MACD line (fast - slow), and signal line (MACD EMA).
    Return a tuple of (macd, signal, histogram).
    """
    fast_ema = calculate_ema(series, fast)
    slow_ema = calculate_ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: int = 2):
    """Calculate rolling mean and rolling std. Return upper_band and lower_band."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper_band = sma + (std_dev * std)
    lower_band = sma - (std_dev * std)
    return upper_band, lower_band, sma

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (Wilder's smoothing).
    TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
    """
    high = df['high']
    low = df['low']
    prev_close = df['close'].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return atr


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate the Volume Weighted Average Price (VWAP).
    typical_price = (High + Low + Close) / 3
    vwap = cumsum(typical_price * volume) / cumsum(volume)
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    cumulative_tp_vol = (typical_price * df['volume']).cumsum()
    cumulative_vol = df['volume'].cumsum()
    return cumulative_tp_vol / cumulative_vol

def calculate_donchian(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Return a DataFrame with highest_high and lowest_low."""
    highest_high = df['high'].rolling(window=period).max()
    lowest_low = df['low'].rolling(window=period).min()
    return pd.DataFrame({'highest_high': highest_high, 'lowest_low': lowest_low})

def calculate_z_score(series: pd.Series, window: int = 20) -> pd.Series:
    """Return the rolling z-score of a series."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    return (series - rolling_mean) / rolling_std
