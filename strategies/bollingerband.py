import pandas as pd
import pandas_ta as ta

def analyze(df: pd.DataFrame) -> dict:
    """
    Bollinger Band Mean Reversion Strategy
    Returns 'BUY' if close <= lower band, 'SELL' if close >= upper band.
    """
    if df is None or df.empty or len(df) < 20:
        return {"signal": "HOLD", "values": {}}

    # Calculate Bollinger Bands (length 20, std 2.0)
    df.ta.bbands(length=20, std=2.0, append=True)
    
    last_row = df.iloc[-1]
    
    close = last_row.get('close')
    bbl = last_row.get('BBL_20_2.0')
    bbu = last_row.get('BBU_20_2.0')
    bbm = last_row.get('BBM_20_2.0')
    
    if pd.isna(bbl) or pd.isna(bbu):
        return {"signal": "HOLD", "values": {}}
        
    signal = "HOLD"
    if close <= bbl:
        signal = "BUY"
    elif close >= bbu:
        signal = "SELL"
        
    return {
        "signal": signal,
        "values": {
            "close": float(close),
            "lower_band": float(bbl),
            "upper_band": float(bbu),
            "middle_band": float(bbm)
        }
    }
