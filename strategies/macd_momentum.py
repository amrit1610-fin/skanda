import pandas as pd
import pandas_ta as ta

def analyze(df: pd.DataFrame) -> dict:
    """
    MACD Momentum Strategy
    Returns 'BUY' when MACD > Signal AND Histogram > 0.
    Returns 'SELL' when MACD < Signal AND Histogram < 0.
    """
    if df is None or df.empty or len(df) < 26:
        return {"signal": "HOLD", "values": {}}

    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    
    last_row = df.iloc[-1]
    macd = last_row.get('MACD_12_26_9')
    macd_signal = last_row.get('MACDs_12_26_9')
    macd_hist = last_row.get('MACDh_12_26_9')
    
    if pd.isna(macd) or pd.isna(macd_signal) or pd.isna(macd_hist):
        return {"signal": "HOLD", "values": {}}
        
    signal = "HOLD"
    if macd > macd_signal and macd_hist > 0:
        signal = "BUY"
    elif macd < macd_signal and macd_hist < 0:
        signal = "SELL"
        
    return {
        "signal": signal,
        "values": {
            "MACD": float(macd),
            "Signal": float(macd_signal),
            "Histogram": float(macd_hist)
        }
    }
