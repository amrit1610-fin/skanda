import os
import ccxt

class AccountManager:
    def __init__(self):
        self.exchange = None

    def initialize_exchange(self, is_paper: bool):
        if is_paper:
            # Paper Trading Mode (Testnet)
            api_key = os.getenv('BINANCE_TESTNET_API_KEY')
            api_secret = os.getenv('BINANCE_TESTNET_SECRET')
            
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
            })
            self.exchange.set_sandbox_mode(True)
            print("[AccountManager] System running in PAPER TRADING mode.")
        else:
            # Live Real-Money Mode (Mainnet)
            api_key = os.getenv('BINANCE_PROD_API_KEY')
            api_secret = os.getenv('BINANCE_PROD_SECRET')
            
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
            })
            self.exchange.set_sandbox_mode(False)
            print("\n" + "="*60)
            print("[AccountManager] CRITICAL WARNING: System running in LIVE REAL-MONEY mode.")
            print("="*60 + "\n")

    def get_exchange(self):
        return self.exchange
