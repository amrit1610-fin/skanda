import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os

def train_conservative_xgboost(data_path="BTCUSD_ml_dataset.csv", model_path="xgboost_btc_model.pkl"):
    if not os.path.exists(data_path):
        print(f"[!] Error: {data_path} not found.")
        return
        
    print(f"[*] Loading dataset from {data_path}...")
    df = pd.read_csv(data_path, index_col=0, parse_dates=True)
    
    features = ['RSI_14', 'Log_Ret_5', 'Tail_Ratio', 'Vol_ZScore', 'BB_Width']
    X = df[features]
    y = df['Target']
    
    # Chronological Split: 80% for train, 20% for final holdout evaluation
    X_train, X_test, y_train, y_test = \
        train_test_split(X, y, test_size=0.2, shuffle=False)
    
    print("[*] Training conservative XGBoost model...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,           # Very shallow to prevent memorizing noise
        learning_rate=0.01,    # Very slow learning
        subsample=0.8,         # Use only 80% of data for each tree
        colsample_bytree=0.8,  # Use only 80% of features for each tree
        eval_metric='logloss',
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate on Holdout Test Data
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    print("\n" + "="*30)
    print("   CONSERVATIVE MODEL REPORT")
    print("="*30)
    print(f"Final Test Accuracy: {accuracy * 100:.2f}%")
    print(classification_report(y_test, predictions))
    
    # Export
    joblib.dump(model, model_path)
    print(f"[+] Conservative model saved to: {model_path}")

if __name__ == "__main__":
    train_conservative_xgboost()