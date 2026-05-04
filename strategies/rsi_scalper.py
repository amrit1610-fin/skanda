import pandas as pd

def analyze(df: pd.DataFrame) -> dict:
    """
    RSI Scalper Strategy
    Returns 'BUY' if RSI < 30, 'SELL' if RSI > 70.
    """
    if df is None or df.empty or len(df) < 15:
        return {"signal": "HOLD", "values": {}}

    # Calculate RSI manually without pandas-ta
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    
    # Handle division by zero
    loss = loss.replace(0, 1e-10)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    rsi_val = rsi.iloc[-1]
    
    if pd.isna(rsi_val):
        return {"signal": "HOLD", "values": {}}
        
    signal = "HOLD"
    if rsi_val < 30:
        signal = "BUY"
    elif rsi_val > 70:
        signal = "SELL"
        
    return {
        "signal": signal,
        "values": {
            "RSI_14": float(rsi_val)
        }
    }
