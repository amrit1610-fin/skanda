import React, { useState } from 'react';
import {
  LayoutDashboard, ClipboardList, CalendarDays,
  Zap, ChevronDown, Loader2, Check, Settings2, SlidersHorizontal, FlaskConical
} from 'lucide-react';
import axios from 'axios';

const STRATEGIES = [
  { value: 'ema',       label: 'EMA Crossover',      interval: 3600 },
  { value: 'rsi',       label: 'RSI Scalper',         interval: 60   },
  { value: 'bollinger', label: 'Bollinger Bands',     interval: 1800 },
  { value: 'trendline', label: 'Trendline Breakout',  interval: 3600 },
  { value: 'macd',      label: 'MACD Momentum',       interval: 900  },
];

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard',  icon: LayoutDashboard  },
  { id: 'tradelog',  label: 'Trade Log',  icon: ClipboardList    },
  { id: 'calendar',  label: 'Calendar',   icon: CalendarDays     },
  { id: 'backtest',  label: 'Backtest',   icon: FlaskConical     },
  { id: 'settings',  label: 'Settings',   icon: SlidersHorizontal},
];

const API_BASE = 'http://localhost:8000/api';

function Sidebar({ activePage, onNavigate, activeStrategy, isLive, onStrategyChange }) {
  const [switching,  setSwitching]  = useState(false);
  const [justSaved,  setJustSaved]  = useState(false);
  const [localStrat, setLocalStrat] = useState(activeStrategy ?? 'rsi');

  // Keep local select in sync when server reports a new strategy
  React.useEffect(() => {
    if (activeStrategy && activeStrategy !== localStrat && !switching) {
      setLocalStrat(activeStrategy);
    }
  }, [activeStrategy]);

  const handleSwitch = async (value) => {
    setLocalStrat(value);
    setSwitching(true);
    const chosen = STRATEGIES.find(s => s.value === value);
    try {
      await axios.post(`${API_BASE}/switch-strategy`, {
        strategy:         value,
        interval_seconds: chosen?.interval ?? 3600,
      });
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
      if (onStrategyChange) onStrategyChange();      // trigger parent refetch
    } catch (e) {
      console.error('Strategy switch failed', e);
    }
    setSwitching(false);
  };

  const activeLabel = STRATEGIES.find(s => s.value === (activeStrategy ?? localStrat))?.label
                    ?? activeStrategy
                    ?? '—';

  return (
    <aside className="sidebar">
      {/* ── Logo ────────────────────────────────── */}
      <div className="sidebar-logo">
        <h2>
          <Zap size={18} className="logo-icon" />
          AI Trading Engine
        </h2>
        <p>ReAct Autonomous System</p>
      </div>

      {/* ── Navigation ──────────────────────────── */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`nav-item${activePage === id ? ' active' : ''}`}
            onClick={() => onNavigate(id)}
          >
            <Icon size={17} />
            {label}
          </button>
        ))}
      </nav>

      {/* ── Strategy Switcher ───────────────────── */}
      <div style={{
        padding: '0 12px 16px',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          marginBottom: 8,
          fontSize: '0.68rem', textTransform: 'uppercase',
          letterSpacing: '0.08em', color: 'var(--text-faint)'
        }}>
          <Settings2 size={11} />
          System Controls
        </div>
        <div style={{
          fontSize: '0.65rem', color: 'var(--text-faint)', marginBottom: 10, lineHeight: 1.4,
        }}>
          Active Agent: <span style={{ color: 'var(--color-mint)', fontWeight: 600 }}>Asset Manager</span>
        </div>

        <div style={{ position: 'relative' }}>
          <select
            id="sidebar-strategy-select"
            value={localStrat}
            onChange={e => handleSwitch(e.target.value)}
            disabled={switching}
            style={{
              width: '100%',
              appearance: 'none',
              background: 'var(--bg-surface-2)',
              border: '1px solid var(--border-mint)',
              borderRadius: 9,
              padding: '9px 34px 9px 12px',
              fontSize: '0.82rem',
              fontWeight: 600,
              color: 'var(--color-mint)',
              cursor: switching ? 'wait' : 'pointer',
              outline: 'none',
              opacity: switching ? 0.6 : 1,
              transition: 'box-shadow 0.2s',
            }}
          >
            {STRATEGIES.map(s => (
              <option key={s.value} value={s.value}
                style={{ background: '#000000', color: '#f5f0ff' }}>
                {s.label}
              </option>
            ))}
          </select>

          {/* Right icon */}
          <span style={{
            position: 'absolute', right: 10, top: '50%',
            transform: 'translateY(-50%)', pointerEvents: 'none',
            display: 'flex', alignItems: 'center'
          }}>
            {switching  ? <Loader2 size={13} color="#00FFC2" style={{ animation: 'spin 1s linear infinite' }} /> :
             justSaved  ? <Check   size={13} color="#00FFC2" /> :
                          <ChevronDown size={13} color="#00FFC2" />}
          </span>
        </div>

        {/* Feedback text */}
        <div style={{
          marginTop: 6, fontSize: '0.68rem', minHeight: 16,
          color: justSaved ? 'var(--color-mint)' : switching ? 'var(--text-faint)' : 'transparent',
          transition: 'color 0.2s',
        }}>
          {switching ? 'Applying to engine…' : justSaved ? '✓ Strategy applied' : '·'}
        </div>
      </div>

      {/* ── Footer: Active Strategy + Live badge ─ */}
      <div className="sidebar-footer">
        {/* Real-time badge pulled from /api/status */}
        <div className="strategy-badge">
          <span className="label">Backend Running</span>
          <span className="value" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {isLive ? (
              <>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--color-mint)',
                  boxShadow: '0 0 6px var(--color-mint)',
                  flexShrink: 0,
                }} />
                {activeLabel}
              </>
            ) : '—'}
          </span>
        </div>

        <div className={`live-indicator${isLive ? ' online' : ' offline'}`}>
          <span className={`pulse-dot${isLive ? '' : ' red'}`} />
          {isLive ? 'System Live' : 'Backend Offline'}
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
