import os
import json
import random
import time
import ccxt
from datetime import datetime, timezone
from dotenv import load_dotenv

from .base_agent import ReActAgent
from .risk_manager import RiskManager

# Load environment variables from .env file
load_dotenv()

# ─── Constants ───────────────────────────────────────────────────────────────
RISK_PER_TRADE    = 0.02      # 2% of current balance risked per trade
TRADE_LOG_FILE    = os.path.join(os.path.dirname(__file__), '..', 'logs', 'trade_history.json')

def format_for_binance(symbol: str) -> str:
    """Dynamically converts standard symbols (e.g., BTCUSDT) to Binance CCXT format (BTC/USDT)."""
    symbol = symbol.upper().replace("-", "").replace("_", "")
    if "/" in symbol:
        return symbol.split(":")[0]
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}/USDT"
    return symbol

# ─── Agent ────────────────────────────────────────────────────────────────────

class QuantTrader(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'quant_trader', 'system_prompt.md')
        super().__init__("QuantTrader", skill_path)
        self.risk_manager = RiskManager()
        
        # 1. Initialize LIVE Mainnet Exchange (Only if keys exist)
        mainnet_key = os.getenv("BINANCE_API_KEY", "")
        mainnet_secret = os.getenv("BINANCE_API_SECRET", "")
        
        if mainnet_key and mainnet_secret:
            self.mainnet_exchange = ccxt.binance({
                'apiKey': mainnet_key,
                'secret': mainnet_secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'future'} # or 'spot' based on your preference
            })
        else:
            self.mainnet_exchange = None
            self.think("[!] No mainnet keys found in .env. Live trading is disabled.")
        
        # 2. Initialize PAPER Testnet Exchange
        testnet_key = os.getenv("BINANCE_TESTNET_API_KEY", "")
        testnet_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")
        
        self.testnet_exchange = ccxt.binance({
            'apiKey': testnet_key,
            'secret': testnet_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        # This tells CCXT to route orders to testnet.binance.vision instead of mainnet
        self.testnet_exchange.set_sandbox_mode(True) 
        
        if not testnet_key:
            self.think("[!] WARNING: Binance Testnet API keys not found in .env. Paper trading will fail.")

        self._ensure_log_file()

    # ── Setup ────────────────────────────────────────────────────────────────

    def _ensure_log_file(self):
        os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
        if not os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, 'w') as f:
                json.dump([], f)

    # ── Trade Log ────────────────────────────────────────────────────────────

    def _append_trade(self, record: dict):
        """Thread-safe append to trade_history.json."""
        try:
            with open(TRADE_LOG_FILE, 'r') as f:
                history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = []

        history.append(record)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                with open(TRADE_LOG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(history, f, indent=4)
                break 
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"[QuantTrader] Failed to write to trade_history.json: {e}")
                time.sleep(random.uniform(0.1, 0.5))

    # ── Core Execution ───────────────────────────────────────────────────────

    def execute_trade(self, approved_trade: dict, market_data: dict | None, is_paper: bool = True):
        """
        The Universal Execution Engine.
        Dynamically routes to Binance Mainnet or Binance Testnet based on the UI toggle.
        """
        mode_str = "PAPER" if is_paper else "LIVE"
        self.think(f"Executing trade in {mode_str} mode...")

        # 🚨 FAILSAFE: Abort if live trading is attempted without configured keys
        if not is_paper and not self.mainnet_exchange:
            self.think("[!] FATAL: Attempted to execute LIVE trade without Mainnet API keys.")
            return {"status": "failed", "reason": "Live trading disabled (No API Keys)"}

        # Select the correct exchange network based on the UI toggle
        active_exchange = self.testnet_exchange if is_paper else self.mainnet_exchange

        symbol   = approved_trade.get("symbol", "BTCUSDT")
        strategy = approved_trade.get("strategy_used", "unknown")
        signal   = approved_trade.get("signal_type",   "HOLD").upper()
        
        if signal not in ["BUY", "SELL"]:
            return {"status": "skipped", "reason": "No valid direction"}

        # Fetch current price directly from the active Binance network
        ccxt_symbol = format_for_binance(symbol)
        try:
            ticker = active_exchange.fetch_ticker(ccxt_symbol)
            entry_price = float(ticker.get("last") or ticker.get("close"))
        except Exception as e:
            self.think(f"[!] Failed to fetch price from Binance: {e}")
            return {"status": "failed", "reason": "Exchange price fetch failed"}

        side = "buy" if signal == "BUY" else "sell"
        brackets = self.risk_manager.calculate_trade_brackets(side, entry_price)

        # 1. Fetch Real Balance safely (BUG-04 Fix)
        try:
            self.think(f"Fetching {mode_str} USDT balance from Binance...")
            balance_data = active_exchange.fetch_balance()
            
            # Safely extract USDT, falling back to 0.0 if the account is empty
            usdt_info = balance_data.get('USDT') or balance_data.get('total', {})
            available_usdt = float((usdt_info or {}).get('free', 0.0))
            
            if available_usdt <= 0:
                self.think(f"[!] {mode_str} USDT balance is zero or not found.")
                return {"status": "failed", "reason": "Zero USDT balance"}
                
        except Exception as e:
            self.think(f"[!] Failed to fetch Binance balance: {e}.")
            return {"status": "failed", "reason": "Could not fetch exchange balance"}
        
        # 2. Position Sizing
        risk_amount = available_usdt * RISK_PER_TRADE  
        amount = round(risk_amount / entry_price, 6)
        
        if risk_amount < 10.0:
            self.think(f"[!] Trade size ({risk_amount:.2f} USDT) below Binance minimums. Skipping.")
            return {"status": "skipped", "reason": "Trade size below exchange minimum"}
        
        params = {
            'stopLossPrice': brackets['stop_loss'],
            'takeProfitPrice': brackets['take_profit']
        }

        # 3. Execution
        try:
            order = active_exchange.create_order(ccxt_symbol, 'limit', side, amount, entry_price, params)
            self.think(f"[QuantTrader] {mode.upper()} LIMIT {side} placed at {entry_price}")
            
            status_flag = "live_executed" if mode == "live" else "paper_executed"
            record = self._build_record(symbol, strategy, signal, entry_price, amount, approved_trade, status_flag)
            self._append_trade(record)
            
            return {"status": "success", "fill_price": entry_price}
            
        except Exception as e:
            self.think(f"{mode.upper()} Order Execution Failed: {e}")
            return {"status": "failed", "reason": str(e)}

    def _build_record(self, symbol, strategy, signal, price, quantity, approved_trade, status):
        return {
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "symbol":          symbol,
            "strategy_used":   strategy,
            "signal_type":     signal,
            "side":            "LONG" if signal == "BUY" else "SHORT",
            "status":          status,
            "win_probability": approved_trade.get("win_probability", 0),
            "sentiment_score": approved_trade.get("sentiment_score", 0),
            "execution_price": round(price, 4),
            "quantity":        round(quantity, 6),
        }

    def log_trade_event(self, strategy_used, signal_type, win_probability, sentiment_score, status, **kwargs):
        """Veto log writer used by Risk Manager."""
        st = (signal_type or "HOLD").upper()
        side = "LONG" if st == "BUY" else "SHORT" if st == "SELL" else "FLAT"
        
        record = {
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "symbol":          kwargs.get("symbol", "BTCUSDT"),
            "strategy_used":   strategy_used,
            "signal_type":     st,
            "side":            side,
            "win_probability": win_probability,
            "sentiment_score": sentiment_score,
            "status":          status,
            "reason":          kwargs.get("reason", ""),
        }
        self._append_trade(record)

    def get_backtest_logs(self) -> list:
        try:
            with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
            return [t for t in history if t.get("status") == "paper_executed"]
        except (FileNotFoundError, json.JSONDecodeError):
            return []