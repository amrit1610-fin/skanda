import React, { useState } from 'react';
import { FlaskConical, Play, AlertCircle, CheckCircle, BarChart3 } from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

const UNIVERSE = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'LTCUSDT',
  'AVAXUSDT', 'DOGEUSDT', 'DOTUSDT', 'LINKUSDT', 'ADAUSDT',
];

const STRATEGIES = [
  { value: 'ema',       label: 'EMA Crossover' },
  { value: 'rsi',       label: 'RSI Scalper' },
  { value: 'bollinger', label: 'Bollinger Bands' },
  { value: 'trendline', label: 'Trendline Breakout' },
  { value: 'macd',      label: 'MACD Momentum' },
];

const TIMEFRAMES = [
  { value: '5m',  label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h',  label: '1h' },
  { value: '4h',  label: '4h' },
];

function BacktestPage() {
  const [symbol, setSymbol]   = useState('BTCUSDT');
  const [strategy, setStrategy] = useState('ema');
  const [timeframe, setTimeframe] = useState('1h');
  const [months, setMonths]   = useState(6);
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);
  const [error, setError]     = useState('');

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

  return (
    <div className="fade-in page-theme-backtest">
      <div className="page-header">
        <div>
          <h1 className="page-title">Strategy Backtest</h1>
          <p className="page-subtitle">
            Six-month (configurable) offline simulation — synthetic OHLCV, same strategy modules as live
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
        <div className="settings-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22 }}>
            <FlaskConical size={18} color="var(--color-mint)" />
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              Backtest Parameters
            </span>
          </div>

          <div className="settings-group">
            <label className="settings-label">Symbol</label>
            <select
              className="settings-select"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
            >
              {UNIVERSE.map(s => (
                <option key={s} value={s}>{s.replace('USDT', '')} / USDT</option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label className="settings-label">Strategy</label>
            <select
              className="settings-select"
              value={strategy}
              onChange={e => setStrategy(e.target.value)}
            >
              {STRATEGIES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label className="settings-label">Bar timeframe</label>
            <select
              className="settings-select"
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
            >
              {TIMEFRAMES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label className="settings-label">History (months)</label>
            <input
              type="number"
              min={1}
              max={24}
              className="settings-select"
              style={{ paddingLeft: 14 }}
              value={months}
              onChange={e => setMonths(Math.max(1, Math.min(24, parseInt(e.target.value, 10) || 6)))}
            />
          </div>

          <div className="settings-divider" />

          <button
            type="button"
            className="settings-save-btn"
            onClick={run}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
          >
            {loading ? 'Running…' : (<><Play size={16} /> Run backtest</>)}
          </button>

          {error && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginTop: 14,
              color: 'var(--color-red)', fontSize: '0.85rem', fontWeight: 600,
            }}>
              <AlertCircle size={15} /> {error}
            </div>
          )}
        </div>

        <div className="settings-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <BarChart3 size={18} color="var(--color-mint)" />
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              Results
            </span>
          </div>

          {!result && !error && (
            <p style={{ fontSize: '0.85rem', color: 'var(--text-faint)', lineHeight: 1.6 }}>
              Run a backtest to see win rate, Sharpe, drawdown, and round-trip count. Metrics use only
              simulated fills (no live veto layer).
            </p>
          )}

          {result && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, color: 'var(--color-mint)' }}>
                <CheckCircle size={16} />
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Completed</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Symbol</span>
                <span className="settings-info-value">{result.symbol}</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Strategy</span>
                <span className="settings-info-value">{result.strategy}</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Timeframe</span>
                <span className="settings-info-value">{result.timeframe}</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Bars</span>
                <span className="settings-info-value">{result.bars?.toLocaleString?.() ?? result.bars}</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Total trades</span>
                <span className="settings-info-value">{result.total_trades}</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Win rate</span>
                <span className="settings-info-value">{result.win_rate_percent}%</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Sharpe</span>
                <span className="settings-info-value">{result.sharpe_ratio}</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Max drawdown</span>
                <span className="settings-info-value">{result.max_drawdown_percent}%</span>
              </div>
              <div className="settings-info-row">
                <span className="settings-info-key">Equity multiple</span>
                <span className="settings-info-value">{result.final_equity_multiple}×</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default BacktestPage;
