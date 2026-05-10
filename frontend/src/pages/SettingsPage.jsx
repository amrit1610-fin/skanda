import React, { useState, useEffect } from 'react';
import { Save, CheckCircle, AlertCircle, Settings, Clock, Cpu, Info } from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

const UNIVERSE = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'LTCUSDT',
  'AVAXUSDT', 'DOGEUSDT', 'DOTUSDT', 'LINKUSDT', 'ADAUSDT',
];

const STRATEGIES = [
  { value: 'ema_8_30', label: '8/30 EMA Momentum (Wizard)', desc: 'Identify momentum expansion. Enter on the first pullback retesting the 8 EMA.' },
  { value: 'ema_9_15', label: '9/15 EMA Scalping (Trade Room)', desc: 'Exploit micro-trend liquidity vacuums with fanned EMAs.' },
  { value: 'trendline_break', label: 'Multi-TF Trendline Break (Tori)', desc: 'Capitalize on fractal market structure shifts.' },
];

const TIMEFRAMES = [
  { value: '5m',   label: '5 min  — Scalping',    interval: 60,   desc: 'High frequency, tight stops'      },
  { value: '15m',  label: '15 min — Intraday',    interval: 300,  desc: 'Short-term intraday momentum'     },
  { value: '1h',   label: '1 hr   — Swing',       interval: 1800, desc: 'Medium-term swing trades'         },
  { value: '4h',   label: '4 hr   — Positional',  interval: 3600, desc: 'Longer-duration position holds'   },
];

function SettingsPage({ status, onSaved }) {
  const [strategy,  setStrategy]  = useState(status?.strategy  ?? 'ema_8_30');
  const [timeframe, setTimeframe] = useState(status?.timeframe ?? '5m');
  const [symbol,    setSymbol]    = useState(status?.symbol ?? 'BTCUSDT');
  const [saving,    setSaving]    = useState(false);
  const [result,    setResult]    = useState(null);   // 'success' | 'error'
  const [errorMsg,  setErrorMsg]  = useState('');

  // Sync when status prop changes (backend hot-update)
  useEffect(() => {
    if (status?.strategy)  setStrategy(status.strategy);
    if (status?.timeframe) setTimeframe(status.timeframe);
    if (status?.symbol)     setSymbol(status.symbol);
  }, [status?.strategy, status?.timeframe, status?.symbol]);

  const currentTF   = TIMEFRAMES.find(t => t.value === timeframe) ?? TIMEFRAMES[0];
  const currentStrat = STRATEGIES.find(s => s.value === strategy)  ?? STRATEGIES[0];

  const handleSave = async () => {
    setSaving(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/update-config`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy,
          timeframe,
          interval_seconds: currentTF.interval,
          symbol,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const d = err?.detail;
        const detailMsg = Array.isArray(d)
          ? d.map(x => x.msg ?? JSON.stringify(x)).join('; ')
          : (typeof d === 'string' ? d : d?.msg);
        throw new Error(detailMsg || err?.error || `HTTP ${res.status}`);
      }

      setResult('success');
      if (onSaved) onSaved();
      setTimeout(() => setResult(null), 3500);
    } catch (e) {
      console.error('Settings save failed:', e);
      setErrorMsg(e?.message ?? 'Network error — is the backend running?');
      setResult('error');
      setTimeout(() => setResult(null), 5000);
    }
    setSaving(false);
  };

  return (
    <div className="fade-in page-theme-settings">
      {/* ── Page Header ──────────────────────────── */}
      <div className="page-header">
        <div>
          <h1 className="page-title">System Settings</h1>
          <p className="page-subtitle">Configure the active trading strategy and execution timeframe</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>

        {/* ── Configuration Form ───────────────────── */}
        <div className="settings-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
            <Settings size={18} color="var(--color-mint)" />
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              Engine Configuration
            </span>
          </div>

          {/* Strategy */}
          <div className="settings-group">
            <label className="settings-label">
              <Cpu size={11} style={{ display: 'inline', marginRight: 5 }} />
              Active Strategy
            </label>
            <select
              id="settings-strategy-select"
              className="settings-select"
              value={strategy}
              onChange={e => setStrategy(e.target.value)}
            >
              {STRATEGIES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <p style={{ fontSize: '0.73rem', color: 'var(--text-faint)', marginTop: 6 }}>
              {currentStrat.desc}
            </p>
          </div>

          {/* Primary symbol */}
          <div className="settings-group">
            <label className="settings-label">Primary symbol (multi-coin universe)</label>
            <select
              id="settings-symbol-select"
              className="settings-select"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
            >
              {UNIVERSE.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <p style={{ fontSize: '0.73rem', color: 'var(--text-faint)', marginTop: 6 }}>
              The <strong style={{ color: 'var(--text-muted)' }}>Asset Manager</strong> scores lead–lag across all{' '}
              {UNIVERSE.length} symbols; execution uses this symbol’s book.
            </p>
          </div>

          {/* Timeframe */}
          <div className="settings-group">
            <label className="settings-label">
              <Clock size={11} style={{ display: 'inline', marginRight: 5 }} />
              Execution Timeframe
            </label>
            <select
              id="settings-timeframe-select"
              className="settings-select"
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
            >
              {TIMEFRAMES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p style={{ fontSize: '0.73rem', color: 'var(--text-faint)', marginTop: 6 }}>
              {currentTF.desc} · Loop interval: {currentTF.interval}s
            </p>
          </div>

          <div className="settings-divider" />

          {/* Save Button */}
          <button
            id="settings-save-btn"
            className="settings-save-btn"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving…' : 'Save Settings'}
          </button>

          {/* Feedback */}
          {result === 'success' && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              marginTop: 14, color: 'var(--color-mint)', fontSize: '0.85rem', fontWeight: 600,
            }}>
              <CheckCircle size={15} />
              Settings saved — engine will apply on next cycle
            </div>
          )}
          {result === 'error' && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              marginTop: 14, color: 'var(--color-red)', fontSize: '0.85rem', fontWeight: 600,
            }}>
              <AlertCircle size={15} />
              {errorMsg || 'Save failed — is the backend running?'}
            </div>
          )}
        </div>

        {/* ── Right: Current Config Info ──────────── */}
        <div className="settings-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <Info size={18} color="var(--color-mint)" />
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              Live Backend Config
            </span>
          </div>

          <div className="settings-info-row">
            <span className="settings-info-key">Active Strategy</span>
            <span className="settings-info-value">
              {STRATEGIES.find(s => s.value === (status?.strategy ?? strategy))?.label ?? '—'}
            </span>
          </div>
          <div className="settings-info-row">
            <span className="settings-info-key">Timeframe</span>
            <span className="settings-info-value">
              {TIMEFRAMES.find(t => t.value === (status?.timeframe ?? timeframe))?.label?.split('—')[0].trim() ?? '—'}
            </span>
          </div>
          <div className="settings-info-row">
            <span className="settings-info-key">Loop Interval</span>
            <span className="settings-info-value">{status?.interval_seconds ?? currentTF.interval}s</span>
          </div>
          <div className="settings-info-row">
            <span className="settings-info-key">Symbol</span>
            <span className="settings-info-value">{status?.symbol ?? symbol}</span>
          </div>
          <div className="settings-info-row">
            <span className="settings-info-key">Backend Status</span>
            <span className="settings-info-value" style={{ color: status?.online ? 'var(--color-mint)' : 'var(--color-red)' }}>
              {status?.online ? 'Online ●' : 'Offline ✕'}
            </span>
          </div>
          <div className="settings-info-row">
            <span className="settings-info-key">Active Agent (multi-coin)</span>
            <span className="settings-info-value">Asset Manager</span>
          </div>

          <div className="settings-divider" />

          {/* Strategy quick-switch note */}
          <p style={{ fontSize: '0.75rem', color: 'var(--text-faint)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--text-muted)' }}>Hot-reload:</strong> The trading engine reads{' '}
            <code style={{ color: 'var(--color-mint)', fontSize: '0.7rem' }}>active_policy.json</code> at the
            start of every cycle. Changes apply without a restart.
          </p>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
