import yfinance as yf
import pandas as pd
import numpy as np
import os

def fetch_and_engineer_data(symbol="BTC-USD", period="4y", interval="1d"):
    print(f"[*] Fetching {period} of {interval} data for {symbol}...")
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    
    # yfinance sometimes returns multi-index columns, flatten them if necessary
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        
    df.dropna(inplace=True)
    
    print("[*] Engineering Institutional Features...")
    # 1. Momentum & Mean Reversion
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # 2. Volatility Squeeze (Bollinger Band Width)
    sma20 = df['Close'].rolling(window=20).mean()
    std20 = df['Close'].rolling(window=20).std()
    df['BB_Width'] = (std20 * 4) / sma20 * 100  # Normalized width
    
    # 3. Multi-Day Returns (Log Returns)
    df['Log_Ret_1'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Log_Ret_5'] = np.log(df['Close'] / df['Close'].shift(5))
    
    # 4. Candle Structure (Exhaustion detection)
    candle_range = df['High'] - df['Low']
    body_size = (df['Close'] - df['Open']).abs()
    df['Tail_Ratio'] = (candle_range - body_size) / (candle_range + 1e-9)
    
    # 5. Trend Intensity (Rolling Z-Score of Volume)
    vol_mean = df['Volume'].rolling(20).mean()
    vol_std = df['Volume'].rolling(20).std()
    df['Vol_ZScore'] = (df['Volume'] - vol_mean) / (vol_std + 1e-9)
    
    # 6. Target Variable (2-Day Horizon)
    df['Target'] = (df['Close'].shift(-2) > df['Close']).astype(int)
    
    df.dropna(inplace=True)
   
    
    # Save to CSV for the ML model to read
    output_file = f"{symbol.replace('-', '')}_ml_dataset.csv"
    df.to_csv(output_file)
    print(f"[+] Successfully generated dataset with {len(df)} rows and {len(df.columns)} features.")
    print(f"[+] Saved to: {output_file}")
    
    return df

if __name__ == "__main__":
    # For ML, we want lots of data. Let's pull 4 years of daily data.
    dataset = fetch_and_engineer_data()
    
    # Print a quick preview of the features and the target
    features = ['RSI_14', 'Log_Ret_5', 'Tail_Ratio', 'Vol_ZScore', 'BB_Width']
    print("\nPreview of ML Dataset:")
    print(dataset[features].tail())