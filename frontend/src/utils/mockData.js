// ─────────────────────────────────────────────────────────────────────────────
// src/utils/mockData.js
// Realistic demo-mode payloads that exactly mirror the FastAPI WebSocket shape.
// Used when isDemoMode === true (backend unreachable on Vercel).
// ─────────────────────────────────────────────────────────────────────────────

// ── Helpers ──────────────────────────────────────────────────────────────────

function isoAgo(minutesBack) {
  return new Date(Date.now() - minutesBack * 60_000).toISOString();
}

function rand(min, max, decimals = 2) {
  return parseFloat((Math.random() * (max - min) + min).toFixed(decimals));
}

// ── Static Seed (randomised once per page-load so the demo looks alive) ──────

const SEED_PRICE      = rand(62_800, 68_400, 2);
const SEED_WIN_RATE   = rand(54, 67, 1);
const SEED_BALANCE    = rand(10_200, 11_850, 2);
const SEED_SHARPE     = rand(1.12, 2.34, 2);
const SEED_DRAWDOWN   = rand(3.1, 8.9, 1);
const SEED_AVG_WIN    = rand(1.4, 3.2, 2);
const SEED_AVG_LOSS   = rand(0.8, 1.9, 2);
const SEED_DECAY      = rand(0.71, 0.98, 4);

// ── 1. economistData  (matches economist_data in the WebSocket stream msg) ───

export const MOCK_ECONOMIST_BASE = {
  regime_id:           1,
  regime_name:         'Trend Breakout',
  confidence_pct:      74.3,
  active_strategy:     '8/30 EMA Momentum',
  dominant_regime:     'BULLISH',
  overall_macro_score:  0.38,
  mtf_matrix: {
    '1m':  'SIDEWAYS',
    '5m':  'BULLISH',
    '15m': 'BULLISH',
    '1h':  'STRONG_BULLISH',
    '4h':  'BULLISH',
    '1d':  'SIDEWAYS',
  },
};

// Produces slightly drifted economist data each tick so the radar feels alive.
export function tickedEconomistData(base = MOCK_ECONOMIST_BASE) {
  const drift = rand(-0.06, 0.06, 4);
  const newScore = parseFloat(
    Math.max(-1, Math.min(1, base.overall_macro_score + drift)).toFixed(4)
  );

  // Slightly mutate one random timeframe state
  const TFS   = ['1m', '5m', '15m', '1h', '4h', '1d'];
  const STATES = ['SIDEWAYS', 'BULLISH', 'BEARISH', 'STRONG_BULLISH', 'STRONG_BEARISH'];
  const mutateTf = TFS[Math.floor(Math.random() * TFS.length)];
  // Only mutate low-weight TFs (1m, 5m) to keep the radar realistic
  const shouldMutate = ['1m', '5m'].includes(mutateTf);

  return {
    ...base,
    overall_macro_score: newScore,
    confidence_pct:      parseFloat((base.confidence_pct + rand(-1.5, 1.5, 1)).toFixed(1)),
    dominant_regime:     newScore >= 0.5  ? 'STRONG_BULLISH'
                       : newScore >= 0.15 ? 'BULLISH'
                       : newScore <= -0.5 ? 'STRONG_BEARISH'
                       : newScore <= -0.15? 'BEARISH'
                       : 'SIDEWAYS',
    mtf_matrix: {
      ...base.mtf_matrix,
      ...(shouldMutate
        ? { [mutateTf]: STATES[Math.floor(Math.random() * STATES.length)] }
        : {}),
    },
  };
}

// ── 2. balance  (matches /api/balance response) ───────────────────────────────

export const MOCK_BALANCE = {
  balance_usdt:    SEED_BALANCE,
  initial_capital: 10_000.00,
  currency:        'USDT',
  trade_count:     23,
};

// ── 3. status  (matches /api/status response) ─────────────────────────────────

export const MOCK_STATUS = {
  online:                     true,
  strategy:                   'ema_8_30',
  timeframe:                  '5m',
  interval_seconds:           300,
  symbol:                     'BTCUSDT',
  asset_manager_active:       true,
  latest_signal_decay:        SEED_DECAY,
  alpha_half_life_seconds:    300,
  alpha_decay_veto_threshold: 0.5,
};

// ── 4. trade logs  (matches /api/logs response array) ─────────────────────────

const MOCK_TRADES_RAW = [
  { minutesBack: 8,   symbol: 'BTCUSDT', signal: 'BUY',  strategy: 'ema_8_30',        price: 67_342.10, pnl:  0.0231, status: 'executed' },
  { minutesBack: 35,  symbol: 'ETHUSDT', signal: 'SELL', strategy: 'ema_9_15',         price: 3_541.80,  pnl: -0.0089, status: 'executed' },
  { minutesBack: 62,  symbol: 'BTCUSDT', signal: 'BUY',  strategy: 'trendline_break',  price: 66_890.50, pnl:  0.0412, status: 'executed' },
  { minutesBack: 94,  symbol: 'SOLUSDT', signal: 'BUY',  strategy: 'ema_8_30',         price:   168.74,  pnl:  0.0178, status: 'executed' },
  { minutesBack: 120, symbol: 'BTCUSDT', signal: 'SELL', strategy: 'ema_9_15',         price: 65_210.00, pnl: -0.0124, status: 'vetoed'   },
  { minutesBack: 145, symbol: 'ETHUSDT', signal: 'BUY',  strategy: 'ema_8_30',         price: 3_489.20,  pnl:  0.0298, status: 'executed' },
  { minutesBack: 178, symbol: 'BNBUSDT', signal: 'BUY',  strategy: 'trendline_break',  price:   591.40,  pnl: -0.0067, status: 'executed' },
  { minutesBack: 210, symbol: 'BTCUSDT', signal: 'BUY',  strategy: 'ema_8_30',         price: 64_780.00, pnl:  0.0553, status: 'executed' },
  { minutesBack: 248, symbol: 'SOLUSDT', signal: 'SELL', strategy: 'ema_9_15',         price:   161.20,  pnl:  0.0089, status: 'vetoed'   },
  { minutesBack: 290, symbol: 'BTCUSDT', signal: 'SELL', strategy: 'trendline_break',  price: 63_410.00, pnl: -0.0198, status: 'executed' },
];

export const MOCK_LOGS = MOCK_TRADES_RAW.map((t, i) => ({
  timestamp:       isoAgo(t.minutesBack),
  symbol:          t.symbol,
  strategy_used:   t.strategy,
  signal_type:     t.signal,
  side:            t.signal === 'BUY' ? 'LONG' : 'SHORT',
  status:          t.status,
  execution_price: t.price,
  entry_price:     t.price,
  win_probability: rand(55, 82, 1),
  sentiment_score: rand(-0.3, 0.7, 4),
  pnl:             t.pnl,
  pnl_usdt:        parseFloat((t.pnl * 200).toFixed(2)),
  reason:          t.status === 'vetoed' ? 'ML Win Probability < 55%' : '',
  decay_factor:    rand(0.55, 0.99, 4),
  id:              `demo-${i}`,
}));

// ── 5. analytics  (matches /api/analytics response) ──────────────────────────

// Build a synthetic equity curve starting from 10_000
const equity = [];
let eq = 10_000;
for (let d = 29; d >= 0; d--) {
  eq = parseFloat((eq * (1 + rand(-0.008, 0.018, 4))).toFixed(2));
  const dt = new Date(Date.now() - d * 86_400_000);
  equity.push({ date: dt.toISOString().slice(0, 10), balance: eq });
}

// Build daily PnL object  { "YYYY-MM-DD": pnl_usdt }
const dailyPnl = {};
equity.forEach((pt, i) => {
  if (i === 0) return;
  dailyPnl[pt.date] = parseFloat((pt.balance - equity[i - 1].balance).toFixed(2));
});

const globalMetrics = {
  total_trades:        23,
  total_vetoes:        6,
  win_rate_percent:    SEED_WIN_RATE,
  sharpe_ratio:        SEED_SHARPE,
  max_drawdown_percent: SEED_DRAWDOWN,
  avg_win_percent:     SEED_AVG_WIN,
  avg_loss_percent:    SEED_AVG_LOSS,
  equity_curve:        equity,
  daily_pnl:           dailyPnl,
};

export const MOCK_ANALYTICS = {
  global_metrics: globalMetrics,
  by_strategy: {
    ema_8_30: {
      ...globalMetrics,
      total_trades:     10,
      win_rate_percent: rand(55, 70, 1),
      sharpe_ratio:     rand(1.0, 2.1, 2),
    },
    ema_9_15: {
      ...globalMetrics,
      total_trades:     8,
      win_rate_percent: rand(48, 62, 1),
      sharpe_ratio:     rand(0.7, 1.5, 2),
    },
    trendline_break: {
      ...globalMetrics,
      total_trades:     5,
      win_rate_percent: rand(52, 72, 1),
      sharpe_ratio:     rand(1.1, 2.4, 2),
    },
  },
};

// ── 6. Live price ticker (for animated price drift in demo mode) ──────────────

let _livePrice = SEED_PRICE;

export function getNextDemoPrice() {
  _livePrice = parseFloat((_livePrice * (1 + rand(-0.0008, 0.0008, 6))).toFixed(2));
  return _livePrice;
}

export const MOCK_PRICE_SEED = SEED_PRICE;
