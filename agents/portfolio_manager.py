class PortfolioManager:
    def __init__(self, active_strategies: list):
        self.active_strategies = active_strategies

    def allocate_capital(self, total_balance: float) -> dict:
        if not self.active_strategies:
            return {}
        
        allocation = total_balance / len(self.active_strategies)
        return {strategy: allocation for strategy in self.active_strategies}

    def net_signals(self, strategy_signals: dict) -> int:
        total_signal = sum(strategy_signals.values())
        if total_signal > 0:
            return 1
        elif total_signal < 0:
            return -1
        else:
            return 0

    def calculate_blended_risk(self, strategy_signals: dict, atr: float) -> tuple[float, float]:
        profiles = {
            'ema_8_30': (2.0, 4.0),
            'ema_9_15': (0.75, 1.5),
            'trendline_break': (2.0, 5.0)
        }
        
        net_dir = self.net_signals(strategy_signals)
        if net_dir == 0:
            return (0.0, 0.0)
            
        # Find strategies that match the net direction
        matching_strategies = []
        for strategy, signal in strategy_signals.items():
            if (net_dir == 1 and signal > 0) or (net_dir == -1 and signal < 0):
                matching_strategies.append(strategy)
                
        if not matching_strategies:
            return (0.0, 0.0)
            
        total_sl_mult = 0.0
        total_tp_mult = 0.0
        
        for strategy in matching_strategies:
            sl_mult, tp_mult = profiles.get(strategy, (1.5, 3.0))
            total_sl_mult += sl_mult
            total_tp_mult += tp_mult
            
        avg_sl_mult = total_sl_mult / len(matching_strategies)
        avg_tp_mult = total_tp_mult / len(matching_strategies)
        
        return (avg_sl_mult * atr, avg_tp_mult * atr)
