import React, { useState, useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { FlaskConical, Play, AlertCircle, CheckCircle, BarChart3 } from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

const THEME = {
  pageBg: '#FFD1DC',
  surface: '#000000',
  accent: '#A020F0',
  textOnBlack: '#f5f5f5',
  grid: '#333333',
};

const UNIVERSE = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'LTCUSDT',
  'AVAXUSDT', 'DOGEUSDT', 'DOTUSDT', 'LINKUSDT', 'ADAUSDT',
];

const STRATEGIES = [
  { value: 'ema_8_30', label: '8/30 EMA Momentum (Wizard)' },
  { value: 'ema_9_15', label: '9/15 EMA Scalping (Trade Room)' },
  { value: 'trendline_break', label: 'Multi-TF Trendline Break (Tori)' },
];

const TIMEFRAMES = [
  { value: '5m',  label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h',  label: '1h' },
  { value: '4h',  label: '4h' },
];

function KpiCard({ title, value, subtitle, valueColor }) {
  return (
    <div
      style={{
        background: THEME.surface,
        borderRadius: 12,
        padding: '18px 20px',
        border: `1px solid ${THEME.accent}`,
        boxShadow: `0 0 0 1px rgba(160, 32, 240, 0.15)`,
      }}
    >
      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: THEME.accent, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {title}
      </div>
      <div style={{ fontSize: '1.55rem', fontWeight: 800, color: valueColor || THEME.accent, marginTop: 8, fontFamily: 'ui-monospace, monospace' }}>
        {value}
      </div>
      {subtitle && (
        <div style={{ fontSize: '0.78rem', color: THEME.textOnBlack, opacity: 0.75, marginTop: 6 }}>
          {subtitle}
        </div>
      )}
    </div>
  );
}

function BacktestPage() {
  const [symbol, setSymbol]   = useState('BTCUSDT');
  const [strategy, setStrategy] = useState('ema_8_30');
  const [timeframe, setTimeframe] = useState('1h');
  const [months, setMonths]   = useState(6);
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);
  const [error, setError]     = useState('');

  const chartData = useMemo(() => {
    const rawEquity = result?.curve_data || [];
    const rawPrice = result?.price_curve || [];
    if (rawEquity.length === 0 && rawPrice.length === 0) return [];
    
    const map = new Map();
    rawEquity.forEach(r => map.set(r.timestamp, { ...r, equity_curve: Number(r.equity_curve) }));
    rawPrice.forEach(r => {
      const ts = r.time;
      if (map.has(ts)) {
        map.get(ts).price = Number(r.price);
      } else {
        map.set(ts, { timestamp: ts, price: Number(r.price) });
      }
    });
    
    return Array.from(map.values()).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  }, [result]);

  const run = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/run-backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          strategy,
          timeframe,
          months: Number(months),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail?.[0]?.msg ?? data?.error ?? `HTTP ${res.status}`);
      }
      if (data.ok === false) {
        throw new Error(data.error || 'Backtest failed');
      }
      setResult(data);
    } catch (e) {
      setError(e?.message ?? 'Request failed');
    }
    setLoading(false);
  };

  const netProfitStr = result != null && result.total_return_pct != null
    ? `${result.total_return_pct >= 0 ? '+' : ''}${result.total_return_pct}%`
    : '—';
  const sharpeStr = result?.sharpe_ratio != null ? String(result.sharpe_ratio) : '—';
  const maxDdStr = result?.max_drawdown_pct != null ? `${result.max_drawdown_pct}%` : '—';

  return (
    <div
      className="fade-in"
      style={{
        minHeight: '100%',
        background: THEME.pageBg,
        margin: '-24px -24px 0',
        padding: 24,
      }}
    >
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <h1 className="page-title" style={{ color: THEME.accent }}>Strategy Backtest</h1>
          <p className="page-subtitle" style={{ color: '#4a4a4a' }}>
            Vectorized simulation — equity curve, net return, Sharpe, and max drawdown from the API payload
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
        <div
          className="settings-card"
          style={{
            background: THEME.surface,
            color: THEME.textOnBlack,
            border: `1px solid ${THEME.accent}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22 }}>
            <FlaskConical size={18} color={THEME.accent} />
            <span style={{ fontWeight: 700, fontSize: '1rem', color: THEME.accent }}>
              Backtest Parameters
            </span>
          </div>

          <div className="settings-group">
            <label className="settings-label" style={{ color: THEME.textOnBlack }}>Symbol</label>
            <select
              className="settings-select"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              style={{ background: '#111', color: THEME.textOnBlack, borderColor: THEME.accent }}
            >
              {UNIVERSE.map(s => (
                <option key={s} value={s}>{s.replace('USDT', '')} / USDT</option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label className="settings-label" style={{ color: THEME.textOnBlack }}>Strategy</label>
            <select
              className="settings-select"
              value={strategy}
              onChange={e => setStrategy(e.target.value)}
              style={{ background: '#111', color: THEME.textOnBlack, borderColor: THEME.accent }}
            >
              {STRATEGIES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label className="settings-label" style={{ color: THEME.textOnBlack }}>Bar timeframe</label>
            <select
              className="settings-select"
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
              style={{ background: '#111', color: THEME.textOnBlack, borderColor: THEME.accent }}
            >
              {TIMEFRAMES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label className="settings-label" style={{ color: THEME.textOnBlack }}>History (months)</label>
            <input
              type="number"
              min={1}
              max={24}
              className="settings-select"
              style={{ paddingLeft: 14, background: '#111', color: THEME.textOnBlack, borderColor: THEME.accent }}
              value={months}
              onChange={e => setMonths(Math.max(1, Math.min(24, parseInt(e.target.value, 10) || 6)))}
            />
          </div>

          <div className="settings-divider" style={{ borderColor: '#333' }} />

          <button
            type="button"
            className="settings-save-btn"
            onClick={run}
            disabled={loading}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              background: THEME.accent,
              color: '#fff',
              border: 'none',
            }}
          >
            {loading ? 'Running…' : (<><Play size={16} /> Run backtest</>)}
          </button>

          {error && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginTop: 14,
              color: '#ff6b6b', fontSize: '0.85rem', fontWeight: 600,
            }}>
              <AlertCircle size={15} /> {error}
            </div>
          )}
        </div>

        <div
          style={{
            background: THEME.surface,
            color: THEME.textOnBlack,
            borderRadius: 12,
            padding: 22,
            border: `1px solid ${THEME.accent}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <BarChart3 size={18} color={THEME.accent} />
            <span style={{ fontWeight: 700, fontSize: '1rem', color: THEME.accent }}>
              Results
            </span>
          </div>

          {!result && !error && (
            <p style={{ fontSize: '0.85rem', color: THEME.textOnBlack, opacity: 0.7, lineHeight: 1.6 }}>
              Run a backtest to load <strong style={{ color: THEME.accent }}>total_return_pct</strong>,{' '}
              <strong style={{ color: THEME.accent }}>sharpe_ratio</strong>,{' '}
              <strong style={{ color: THEME.accent }}>max_drawdown_pct</strong>, and{' '}
              <strong style={{ color: THEME.accent }}>curve_data</strong> from{' '}
              <code style={{ color: THEME.accent }}>POST /api/run-backtest</code>.
            </p>
          )}

          {result && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, color: THEME.accent }}>
                <CheckCircle size={16} />
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Completed</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
                <KpiCard
                  title="Net profit"
                  value={netProfitStr}
                  subtitle="total_return_pct"
                />
                <KpiCard
                  title="Sharpe ratio"
                  value={sharpeStr}
                  subtitle="Annualized"
                />
                <KpiCard
                  title="Max drawdown"
                  value={maxDdStr}
                  subtitle="max_drawdown_pct"
                />
                <KpiCard
                  title="TOTAL TRADES"
                  value={result?.total_trades != null ? String(result.total_trades) : '—'}
                  subtitle="Executed"
                />
                <KpiCard
                  title="WIN RATE"
                  value={result?.win_rate != null ? `${result.win_rate}%` : '—'}
                  subtitle="Profitable"
                  valueColor={result?.win_rate != null ? (result.win_rate > 50 ? '#4ade80' : '#f87171') : undefined}
                />
              </div>

              <div style={{ fontSize: '0.8rem', color: THEME.textOnBlack, opacity: 0.85, marginBottom: 12 }}>
                <span style={{ color: THEME.accent, fontWeight: 600 }}>{result.symbol}</span>
                {' · '}
                {result.strategy}
                {' · '}
                {result.timeframe}
                {' · '}
                {result.bars?.toLocaleString?.() ?? result.bars} bars
              </div>

              <div style={{ width: '100%', height: 340, marginTop: 8 }}>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="skandaEquityFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={THEME.accent} stopOpacity={0.85} />
                          <stop offset="100%" stopColor={THEME.accent} stopOpacity={0.08} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke={THEME.grid} strokeDasharray="3 3" />
                      <XAxis
                        dataKey="timestamp"
                        tick={{ fill: THEME.accent, fontSize: 9 }}
                        stroke={THEME.grid}
                        interval="preserveStartEnd"
                        minTickGap={28}
                      />
                      <YAxis
                        yAxisId="left"
                        dataKey="equity_curve"
                        tick={{ fill: THEME.accent, fontSize: 10 }}
                        stroke={THEME.grid}
                        domain={['auto', 'auto']}
                        width={48}
                      />
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        dataKey="price"
                        tick={{ fill: '#888888', fontSize: 10 }}
                        stroke={THEME.grid}
                        domain={['auto', 'auto']}
                        width={48}
                      />
                      <Tooltip
                        contentStyle={{
                          background: THEME.surface,
                          border: `1px solid ${THEME.accent}`,
                          borderRadius: 8,
                          color: THEME.textOnBlack,
                        }}
                        labelStyle={{ color: THEME.accent, fontWeight: 700 }}
                        formatter={(v, name) => [Number(v).toFixed(4), name === 'equity_curve' ? 'equity' : 'price']}
                      />
                      <Area
                        yAxisId="left"
                        type="monotone"
                        dataKey="equity_curve"
                        stroke={THEME.accent}
                        strokeWidth={2}
                        fill="url(#skandaEquityFill)"
                        isAnimationActive={false}
                      />
                      <Area
                        yAxisId="right"
                        type="monotone"
                        dataKey="price"
                        stroke="#888888"
                        strokeWidth={2}
                        fill="none"
                        strokeDasharray="5 5"
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ color: THEME.textOnBlack, opacity: 0.6, padding: 24, textAlign: 'center' }}>
                    No curve_data in response
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default BacktestPage;
