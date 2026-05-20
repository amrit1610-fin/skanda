import os
import pandas as pd
import numpy as np
from catboost import CatBoostClassifier, Pool
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# Ensure the models directory exists
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODEL_DIR, 'catboost_model.cbm')

def generate_synthetic_trade_data(num_samples=5000):
    """
    Generates realistic mock data to train the initial baseline model.
    Once you have real trade history, you will replace this function with a CSV loader!
    """
    print(f"[*] Generating {num_samples} synthetic trade records for baseline training...")
    
    signals = ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"]
    strategies = ["ema_8_30", "ema_9_15", "trendline_break"]
    
    data = {
        "quant_signal": np.random.choice(signals, num_samples, p=[0.15, 0.25, 0.2, 0.25, 0.15]),
        "sentiment_score": np.random.uniform(-1.0, 1.0, num_samples),
        "active_strategy": np.random.choice(strategies, num_samples)
    }
    df = pd.DataFrame(data)
    
    # Simulate realistic outcomes (Strong signals + good sentiment = higher chance of winning)
    def determine_outcome(row):
        prob = 0.50
        if "STRONG" in row['quant_signal']: prob += 0.20
        elif row['quant_signal'] in ["BUY", "SELL"]: prob += 0.10
        
        prob += (row['sentiment_score'] * 0.15)
        
        # Add some market randomness
        prob = np.clip(prob + np.random.normal(0, 0.1), 0.0, 1.0)
        return 1 if np.random.rand() < prob else 0

    df['is_profitable'] = df.apply(determine_outcome, axis=1)
    return df

def train_catboost():
    print("--- Skanda ML Training Pipeline ---")
    
    # 1. Load Data (Using synthetic for now, replace with pd.read_csv('your_trades.csv') later)
    df = generate_synthetic_trade_data()
    
    # Define our Features (X) and Target (y)
    X = df[["quant_signal", "sentiment_score", "active_strategy"]]
    y = df["is_profitable"]
    
    # 2. Split into Training and Testing sets (80% train, 20% test)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # CatBoost Needs to know which columns are text/strings!
    categorical_features = ["quant_signal", "active_strategy"]
    
    # Create CatBoost Pools (Optimized data structures)
    train_pool = Pool(X_train, y_train, cat_features=categorical_features)
    test_pool = Pool(X_test, y_test, cat_features=categorical_features)
    
    # 3. Initialize the Model
    # We use CPU here so we don't accidentally max out your RTX 3050 VRAM during testing
    model = CatBoostClassifier(
        iterations=500,
        learning_rate=0.05,
        depth=6,
        loss_function='Logloss',
        eval_metric='Accuracy',
        task_type='CPU',
        random_seed=42,
        verbose=100 # Print progress every 100 steps
    )
    
    # 4. Train the Model
    print("\n[*] Commencing Model Training...")
    model.fit(train_pool, eval_set=test_pool, early_stopping_rounds=50)
    
    # 5. Evaluate the Model
    print("\n[*] Evaluating Model Performance...")
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Validation Accuracy: {acc * 100:.2f}%\n")
    print(classification_report(y_test, preds, target_names=["Loss (0)", "Win (1)"]))
    
    # 6. Save the Model
    model.save_model(MODEL_PATH)
    print(f"[*] SUCCESS! Baseline model saved to: {MODEL_PATH}")

if __name__ == "__main__":
    train_catboost()