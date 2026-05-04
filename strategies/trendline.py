import pandas as pd
import numpy as np
import pandas_ta as ta
from scipy.signal import find_peaks
from scipy.stats import linregress

def analyze(df: pd.DataFrame) -> dict:
    """
    Trendline Breakout Strategy
    Uses last 50 periods to find peaks/troughs and calculate dynamic support/resistance.
    Returns 'BUY' if close breaks resistance upwards.
    Returns 'SELL' if close breaks support downwards.
    """
    window = 50
    # Need extra rows for accurate ATR calculation
    if df is None or df.empty or len(df) < window + 14:
        return {"signal": "HOLD", "values": {}}

    # Calculate ATR (14-period) for dynamic prominence
    df.ta.atr(length=14, append=True)
    
    # Take the last `window` rows for localized pattern detection
    recent = df.tail(window).copy()
    recent.reset_index(drop=True, inplace=True)
    
    highs = recent['high'].values
    lows = recent['low'].values
    closes = recent['close'].values
    atrs = recent['ATRr_14'].values
    
    # Average ATR in this window to establish volatility baseline
    avg_atr = np.nanmean(atrs)
    if np.isnan(avg_atr) or avg_atr == 0:
        dynamic_prominence = 0.5 # fallback
    else:
        dynamic_prominence = 1.5 * avg_atr
    
    # 1. Find potential peaks and troughs based on dynamic prominence
    # Using distance=3 to separate clusters initially
    raw_peaks, _ = find_peaks(highs, prominence=dynamic_prominence, distance=3)
    raw_troughs, _ = find_peaks(-lows, prominence=dynamic_prominence, distance=3)
    
    # 2. Confirmation Logic: Ensure at least 2 lower/higher candles follow the peak/trough
    # Filter out anything too close to the end (must be <= window-3 to have 2 following candles)
    valid_peaks = []
    for p in raw_peaks:
        if p <= window - 3:
            if highs[p] > highs[p+1] and highs[p] > highs[p+2]:
                valid_peaks.append(p)
                
    valid_troughs = []
    for t in raw_troughs:
        if t <= window - 3:
            if lows[t] < lows[t+1] and lows[t] < lows[t+2]:
                valid_troughs.append(t)
                
    peaks = np.array(valid_peaks)
    troughs = np.array(valid_troughs)
    
    res_line_y = None
    sup_line_y = None
    res_slope = None
    sup_slope = None
    
    # 3. Linear Regression for Support/Resistance
    # Calculate Resistance line if at least 2 confirmed peaks exist
    if len(peaks) >= 2:
        res_slope, res_intercept, _, _, _ = linregress(peaks, highs[peaks])
        res_line_y = res_slope * (window - 1) + res_intercept # Projected to current index
        
    # Calculate Support line if at least 2 confirmed troughs exist
    if len(troughs) >= 2:
        sup_slope, sup_intercept, _, _, _ = linregress(troughs, lows[troughs])
        sup_line_y = sup_slope * (window - 1) + sup_intercept # Projected to current index
        
    current_close = closes[-1]
    signal = "HOLD"
    
    # 4. Breakout Detection
    if res_line_y is not None and current_close > res_line_y:
        signal = "BUY"
    elif sup_line_y is not None and current_close < sup_line_y:
        signal = "SELL"
        
    return {
        "signal": signal,
        "values": {
            "close": float(current_close),
            "projected_resistance": float(res_line_y) if res_line_y is not None else None,
            "projected_support": float(sup_line_y) if sup_line_y is not None else None,
            "resistance_slope": float(res_slope) if res_slope is not None else None,
            "support_slope": float(sup_slope) if sup_slope is not None else None,
            "dynamic_prominence": float(dynamic_prominence)
        }
    }
