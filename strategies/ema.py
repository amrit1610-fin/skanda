import pandas as pd
import pandas_ta as ta

def analyze(df: pd.DataFrame) -> dict:
    """
    13/48 EMA Strategy
    Returns 'BUY' on golden cross, 'SELL' on death cross, else 'HOLD'.
    """
    if df is None or df.empty or len(df) < 48:
        return {"signal": "HOLD", "values": {}}

    # Calculate EMAs
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=48, append=True)
    
    # Get last two rows
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    ema_13 = last_row.get('EMA_13')
    ema_48 = last_row.get('EMA_48')
    prev_ema_13 = prev_row.get('EMA_13')
    prev_ema_48 = prev_row.get('EMA_48')
    
    if pd.isna(ema_13) or pd.isna(ema_48):
        return {"signal": "HOLD", "values": {}}
        
    signal = "HOLD"
    
    # Golden cross: fast crosses above slow
    if prev_ema_13 <= prev_ema_48 and ema_13 > ema_48:
        signal = "BUY"
    # Death cross: fast crosses below slow
    elif prev_ema_13 >= prev_ema_48 and ema_13 < ema_48:
        signal = "SELL"
        
    return {
        "signal": signal,
        "values": {
            "EMA_13": float(ema_13),
            "EMA_48": float(ema_48)
        }
    }
