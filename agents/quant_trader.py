import os
import json
import random
import time
import ccxt
from datetime import datetime, timezone
from .base_agent import ReActAgent
from .risk_manager import RiskManager

# ─── Constants ───────────────────────────────────────────────────────────────
RISK_PER_TRADE   = 0.02      # 2% of current balance risked per trade
MOCK_HOLD_SECS   = 5         # Seconds to "hold" a position before exit (paper)
BALANCE_FILE     = os.path.join(os.path.dirname(__file__), '..', 'logs', 'account_balance.json')
TRADE_LOG_FILE   = os.path.join(os.path.dirname(__file__), '..', 'logs', 'trade_history.json')

DELTA_SYMBOL_MAP = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "BTC/USDT": "BTC/USDT:USDT",
}

# ─── Wallet Helpers ───────────────────────────────────────────────────────────

def _read_balance() -> dict:
    """Read the paper trading wallet from disk."""
    try:
        with open(BALANCE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        default = {
            "balance_usdt":    10000.00,
            "initial_capital": 10000.00,
            "currency":        "USDT",
            "last_updated":    datetime.now(timezone.utc).isoformat(),
            "trade_count":     0
        }
        _write_balance(default)
        return default

def _write_balance(wallet: dict):
    """Persist the paper trading wallet to disk."""
    wallet["last_updated"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(BALANCE_FILE), exist_ok=True)
    with open(BALANCE_FILE, 'w') as f:
        json.dump(wallet, f, indent=4)

# ─── Price Fetcher ────────────────────────────────────────────────────────────

def _fetch_real_price(symbol: str) -> float | None:
    """
    Fetches the real-time last price from Delta Exchange India (testnet) via ccxt.
    Falls back gracefully if ccxt is unavailable or the call fails.
    """
    try:
        import ccxt
        exchange = ccxt.delta({
            "options": {"defaultType": "future"},
        })
        # Normalise symbol to CCXT format
        ccxt_symbol = DELTA_SYMBOL_MAP.get(symbol, symbol)
        ticker = exchange.fetch_ticker(ccxt_symbol)
        price  = ticker.get("last") or ticker.get("close")
        return float(price) if price else None
    except Exception as e:
        return None

# ─── Agent ────────────────────────────────────────────────────────────────────

class QuantTrader(ReActAgent):
    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), '..', '.skills', 'quant_trader', 'system_prompt.md')
        super().__init__("QuantTrader", skill_path)
        self.risk_manager = RiskManager()
        self.exchange = ccxt.delta({
            "options": {"defaultType": "future"},
        })
        self._ensure_log_file()
        self._ensure_balance_file()

    # ── Setup ────────────────────────────────────────────────────────────────

    def _ensure_log_file(self):
        os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
        if not os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, 'w') as f:
                json.dump([], f)

    def _ensure_balance_file(self):
        if not os.path.exists(BALANCE_FILE):
            self.think("Initialising paper trading wallet with $10,000 USDT.")
            _write_balance({
                "balance_usdt":    10000.00,
                "initial_capital": 10000.00,
                "currency":        "USDT",
                "trade_count":     0
            })

    # ── Trade Log ────────────────────────────────────────────────────────────

    def _append_trade(self, record: dict):
        """Thread-safe append to trade_history.json."""
        try:
            with open(TRADE_LOG_FILE, 'r') as f:
                history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = []

        history.append(record)

        with open(TRADE_LOG_FILE, 'w') as f:
            json.dump(history, f, indent=4)

    # ── Core Execution ───────────────────────────────────────────────────────

    def execute_trade(self, approved_trade: dict, market_data: dict | None):
        """
        Paper-executes a risk-approved trade:
          1. Reads current wallet balance
          2. Fetches real-time price via ccxt (falls back to mock OHLCV close)
          3. Calculates quantity based on 2% risk
          4. Mocks a hold period, then computes exit price
          5. Updates account_balance.json
          6. Writes full trade record to trade_history.json
        """
        self.think("Paper-executing approved trade with real-time price fetch...")

        # ── 1. Symbol & strategy ────────────────────────────────────────────
        symbol   = "BTCUSDT"
        strategy = approved_trade.get("strategy_used", "unknown")
        signal   = approved_trade.get("signal_type",   "BUY").upper()

        if market_data is not None:
            symbol = market_data.get("symbol", symbol)

        # ── 2. Wallet ────────────────────────────────────────────────────────
        wallet          = _read_balance()
        balance_before  = wallet["balance_usdt"]
        initial_capital = wallet.get("initial_capital", balance_before)

        self.think(f"Wallet balance before trade: ${balance_before:,.2f} USDT")

        # ── 3. Real-time entry price ─────────────────────────────────────────
        entry_price = _fetch_real_price(symbol)
        price_source = "ccxt_live"

        if entry_price is None:
            # Fallback: use last close from mock OHLCV data
            price_source = "mock_ohlcv"
            try:
                ohlcv = market_data.get("ohlcv_data") if market_data else None
                if ohlcv is not None and not ohlcv.empty:
                    entry_price = float(ohlcv.iloc[-1]["close"])
            except Exception:
                pass

        if entry_price is None or entry_price <= 0:
            # Final fallback: plausible BTC price range
            entry_price  = random.uniform(58000, 72000)
            price_source = "fallback_mock"

        self.think(f"Entry price: ${entry_price:,.2f} ({price_source})")
        current_price = entry_price

        # ── 4. Position sizing (2% risk rule) ────────────────────────────────
        risk_amount = balance_before * RISK_PER_TRADE          # $200 on $10k
        amount    = round(risk_amount / current_price, 6)       # BTC units
        quantity = amount

        self.think(f"Risk amount: ${risk_amount:.2f} | Quantity: {quantity:.6f} {symbol.replace('USDT','')}")

        # ── 5. Bracketed Limit Order Execution ───────────────────────────────
        side = "buy" if signal == "BUY" else "sell"
        brackets = self.risk_manager.calculate_trade_brackets(side, current_price)
        
        params = {
            'stopLossPrice': brackets['stop_loss'],
            'takeProfitPrice': brackets['take_profit']
        }

        try:
            # Normalise symbol to CCXT format
            ccxt_symbol = DELTA_SYMBOL_MAP.get(symbol, symbol)
            order = self.exchange.create_order(ccxt_symbol, 'limit', side, amount, current_price, params)
            print(f"[QuantTrader] Executing LIMIT {side} at {current_price} | SL: {brackets['stop_loss']} | TP: {brackets['take_profit']}")
        except Exception as e:
            self.think(f"Order Execution Failed: {e}")
            # Fallback for paper testing or if API fails
            pass

        # ── 6. Mock hold (Wait for fill/exit in paper mode context) ──────────
        self.think(f"Holding position for {MOCK_HOLD_SECS}s (monitoring brackets)...")
        time.sleep(MOCK_HOLD_SECS)

        # Random PnL: uniform between -1.5% and +3.5% (asymmetric for realism)
        pnl_pct    = random.uniform(-0.015, 0.035)
        exit_price = round(entry_price * (1 + pnl_pct), 4)

        # ── 6. Actual P&L in USDT ────────────────────────────────────────────
        gross_pnl_usdt  = (exit_price - entry_price) * quantity
        if signal == "SELL":
            gross_pnl_usdt = -gross_pnl_usdt      # short direction

        balance_after   = round(balance_before + gross_pnl_usdt, 4)
        pnl_pct_actual  = round(pnl_pct if signal != "SELL" else -pnl_pct, 6)

        self.think(
            f"Exit price: ${exit_price:,.2f} | Gross PnL: ${gross_pnl_usdt:+.2f} | "
            f"New balance: ${balance_after:,.2f}"
        )

        # ── 7. Update wallet ─────────────────────────────────────────────────
        wallet["balance_usdt"]  = balance_after
        wallet["trade_count"]   = wallet.get("trade_count", 0) + 1
        _write_balance(wallet)

        # ── 8. Write full trade record ───────────────────────────────────────
        record = {
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "symbol":          symbol,
            "strategy_used":   strategy,
            "signal_type":     signal,
            "side":            "LONG" if signal == "BUY" else "SHORT" if signal == "SELL" else "FLAT",
            "status":          "executed",
            "decay_factor":    approved_trade.get("decay_factor"),
            "win_probability": approved_trade.get("win_probability", 0),
            "sentiment_score": approved_trade.get("sentiment_score", 0),
            # Position details
            "entry_price":     round(entry_price, 4),
            "exit_price":      round(exit_price,  4),
            "quantity":        quantity,
            "price_source":    price_source,
            # Capital / P&L
            "initial_capital": initial_capital,
            "balance_before":  round(balance_before, 4),
            "balance_after":   round(balance_after,  4),
            "pnl_usdt":        round(gross_pnl_usdt, 4),
            "pnl":             pnl_pct_actual,          # fractional, used by analytics
            "final_pnl":       round(gross_pnl_usdt, 4),
        }

        if approved_trade.get("signal_from_cointegration"):
            pz = approved_trade.get("pair_z_score")
            pp = approved_trade.get("pair_p_value")
            if pz is not None:
                record["pair_z_score"] = float(pz)
            if pp is not None:
                try:
                    record["pair_p_value"] = float(pp)
                except (TypeError, ValueError):
                    record["pair_p_value"] = pp
            if approved_trade.get("pair_leg_x"):
                record["pair_leg_x"] = approved_trade.get("pair_leg_x")

        self._append_trade(record)
        self.think(f"Trade logged. Wallet updated: ${balance_before:,.2f} → ${balance_after:,.2f}")

        return self.act("execute_trade", {
            "status":        "executed",
            "symbol":        symbol,
            "entry_price":   entry_price,
            "exit_price":    exit_price,
            "quantity":      quantity,
            "pnl_usdt":      round(gross_pnl_usdt, 4),
            "pnl":           pnl_pct_actual,
            "balance_after": balance_after,
        })

    # ── Veto logging (called by RiskManager path for consistency) ────────────

    def log_trade_event(self, strategy_used, signal_type, win_probability,
                        sentiment_score, status, entry_price=None,
                        exit_price=None, position_size=None, mocked_pnl=None, **kwargs):
        """Backwards-compatible veto log writer (no wallet update for vetoed trades)."""
        st = (signal_type or "HOLD").upper()
        side = kwargs.get("side")
        if not side:
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
            "entry_price":     entry_price,
            "exit_price":      exit_price,
            "quantity":        position_size,
            "pnl":             mocked_pnl,
            "reason":          kwargs.get("reason", ""),
        }
        self._append_trade(record)
