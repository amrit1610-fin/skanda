import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import StatCard    from '../components/StatCard';
import EquityChart from '../components/EquityChart';
import PnLBarChart from '../components/PnLBarChart';
import AccountSwitcher from '../components/AccountSwitcher';
import { BarChart2, Activity, ShieldAlert } from 'lucide-react';

const STRATEGIES = [
  { value: 'global',        label: 'All Strategies (Global)' },
  { value: 'ema_8_30',      label: '8/30 EMA Momentum (Wizard)' },
  { value: 'ema_9_15',      label: '9/15 EMA Scalping (Trade Room)' },
  { value: 'trendline_break', label: 'Multi-TF Trendline Break (Tori)' },
];

const API_BASE = 'http://localhost:8000/api';
const MANUAL_STRATEGIES = ['ema_8_30', 'ema_9_15', 'trendline_break'];

function DashboardPage({ analytics, status, balance, economistData, onStrategyChange, tradingMode, onToggleMode, systemMode, setSystemMode }) {
  const [selectedStrategy, setSelectedStrategy] = useState('global');
  const [manualStrategy, setManualStrategy] = useState(status?.strategy ?? 'ema_8_30');

  useEffect(() => {
    if (status?.strategy) {
      setManualStrategy(status.strategy);
    }
  }, [status?.strategy]);

  const bannerTheme = useMemo(() => {
    const regimeId = economistData?.regime_id;
    if (regimeId === 2) {
      return { border: 'rgba(252,92,101,0.45)', glow: 'rgba(252,92,101,0.20)', text: '#fca5a5', accent: '#FC5C65' };
    }
    if (regimeId === 1) {
      return { border: 'rgba(250,204,21,0.45)', glow: 'rgba(250,204,21,0.20)', text: '#fde68a', accent: '#facc15' };
    }
    return { border: 'rgba(0,255,194,0.45)', glow: 'rgba(0,255,194,0.18)', text: '#7efce2', accent: '#00FFC2' };
  }, [economistData]);

  const submitManualStrategy = async (strategy) => {
    try {
      await axios.post(`${API_BASE}/switch-strategy`, {
        strategy,
        interval_seconds: Number(status?.interval_seconds ?? 3600),
      });
      onStrategyChange?.();
    } catch {
      // keep dashboard resilient even if backend is briefly unavailable
    }
  };

  const isGlobal = selectedStrategy === 'global';
  const metrics  = isGlobal
    ? analytics?.global_metrics
    : analytics?.by_strategy?.[selectedStrategy];

  const winRate      = metrics?.win_rate_percent     ?? null;
  const sharpe       = metrics?.sharpe_ratio         ?? null;
  const drawdown     = metrics?.max_drawdown_percent ?? null;
  // total_trades from backend is now ONLY executed trades (vetoes excluded at source)
  const totalTrades  = isGlobal
    ? analytics?.global_metrics?.total_trades ?? null
    : metrics?.total_trades ?? null;
  const totalVetoes = analytics?.global_metrics?.total_vetoes ?? null;
  const avgWin  = metrics?.avg_win_percent  ?? null;
  const avgLoss = metrics?.avg_loss_percent ?? null;

  const equityCurve = metrics?.equity_curve ?? [];
  const dailyPnl    = metrics?.daily_pnl    ?? {};

  // ── Balance metrics ────────────────────────────────────────────────────────
  const currentBalance  = balance?.balance_usdt    ?? null;
  const initialCapital  = balance?.initial_capital ?? null;
  const balancePnlUsdt  = (currentBalance != null && initialCapital != null) ? currentBalance - initialCapital : null;
  const balancePnlPct   = (currentBalance != null && initialCapital != null && initialCapital > 0)
    ? ((currentBalance - initialCapital) / initialCapital * 100).toFixed(2)
    : null;

  return (
    <div className="fade-in">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'flex-end' }}>
        <AccountSwitcher tradingMode={tradingMode} onToggleMode={onToggleMode} />
      </div>
      <div
        className="card"
        style={{
          marginBottom: 16,
          borderColor: bannerTheme.border,
          boxShadow: `0 0 0 1px ${bannerTheme.border}, 0 0 28px ${bannerTheme.glow}`,
          background: 'linear-gradient(120deg, rgba(17,24,39,0.94) 0%, rgba(9,14,24,0.98) 100%)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: '0.72rem', letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
              Macro Economist
            </div>
            <div style={{ fontSize: '1.12rem', fontWeight: 700, color: bannerTheme.text }}>
              {economistData?.regime_name ?? 'Sideways / Mean Reversion'}
            </div>
            <div style={{ marginTop: 2, color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
              Confidence: {economistData?.confidence_pct != null ? `${Number(economistData.confidence_pct).toFixed(1)}%` : '--'}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>System Mode</span>
              <button
                type="button"
                onClick={() => setSystemMode((m) => (m === 'auto' ? 'manual' : 'auto'))}
                style={{
                  position: 'relative',
                  width: 74,
                  height: 34,
                  borderRadius: 999,
                  border: `1px solid ${systemMode === 'auto' ? 'rgba(0,255,194,0.55)' : 'rgba(252,92,101,0.55)'}`,
                  background: systemMode === 'auto' ? 'rgba(0,255,194,0.14)' : 'rgba(252,92,101,0.16)',
                  cursor: 'pointer',
                }}
                aria-label="System Mode: Auto-Pilot / Manual Override"
                title={`System Mode: ${systemMode === 'auto' ? 'Auto-Pilot' : 'Manual Override'}`}
              >
                <span
                  style={{
                    position: 'absolute',
                    top: 3,
                    left: systemMode === 'auto' ? 40 : 3,
                    width: 26,
                    height: 26,
                    borderRadius: '50%',
                    background: systemMode === 'auto' ? '#00FFC2' : '#FC5C65',
                    boxShadow: systemMode === 'auto' ? '0 0 18px rgba(0,255,194,0.5)' : '0 0 18px rgba(252,92,101,0.45)',
                    transition: 'left 0.2s ease',
                  }}
                />
              </button>
              <span className={`pill ${systemMode === 'auto' ? 'mint' : 'red'}`}>
                {systemMode === 'auto' ? 'Auto-Pilot' : 'Manual Override'}
              </span>
            </div>

            {systemMode === 'auto' ? (
              <div style={{ minWidth: 230 }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 3 }}>
                  Active Strategy (AI Directed)
                </div>
                <div
                  style={{
                    color: bannerTheme.accent,
                    textShadow: `0 0 10px ${bannerTheme.glow}`,
                    fontWeight: 700,
                    fontSize: '0.95rem',
                  }}
                >
                  {economistData?.active_strategy ?? '8/30 EMA Momentum'}
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <select
                  className="strategy-select"
                  value={manualStrategy}
                  onChange={async (e) => {
                    const next = e.target.value;
                    setManualStrategy(next);
                    await submitManualStrategy(next);
                  }}
                >
                  {MANUAL_STRATEGIES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#fca5a5', fontSize: '0.78rem' }}>
                  <ShieldAlert size={14} />
                  AI council disabled while in manual mode
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Page Header + Strategy Filter */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Real-time portfolio analytics &amp; performance</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>View:</span>
          <select
            id="strategy-filter-select"
            className="strategy-select"
            value={selectedStrategy}
            onChange={e => setSelectedStrategy(e.target.value)}
          >
            {STRATEGIES.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Stat Cards — 8 columns */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 14, marginBottom: 24 }}>
        <StatCard
          title="Current Balance"
          value={currentBalance != null ? `$${currentBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '--'}
          subtitle={
            balancePnlUsdt != null
              ? `${balancePnlUsdt >= 0 ? '+' : ''}$${balancePnlUsdt.toFixed(2)} (${balancePnlPct >= 0 ? '+' : ''}${balancePnlPct}%)`
              : tradingMode === 'real' ? 'Live Execution Active' : 'Paper Environment'
          }
          colorClass={balancePnlUsdt == null ? 'neutral' : balancePnlUsdt >= 0 ? 'mint' : 'red'}
        />
        <StatCard
          title="Sharpe Ratio"
          value={sharpe != null ? sharpe.toFixed(2) : '--'}
          subtitle="Risk-adjusted return"
          colorClass={sharpe == null ? 'neutral' : sharpe >= 1 ? 'mint' : sharpe < 0 ? 'red' : 'neutral'}
        />
        <StatCard
          title="Max Drawdown"
          value={drawdown != null ? `-${drawdown}%` : '--'}
          subtitle="Peak-to-trough"
          colorClass={drawdown == null ? 'neutral' : drawdown > 20 ? 'red' : 'mint'}
        />
        <StatCard
          title="Win Rate"
          value={winRate != null ? `${winRate}%` : '--'}
          subtitle="Executed trades"
          colorClass={winRate == null ? 'neutral' : winRate >= 50 ? 'mint' : 'red'}
          showPie={winRate != null}
          pieValue={winRate ?? 0}
        />
        <StatCard
          title="Total Trades"
          value={totalTrades ?? '0'}
          subtitle={
            isGlobal
              ? `Executed only${totalVetoes != null ? ` · ${totalVetoes} vetoed` : ''}`
              : STRATEGIES.find(s=>s.value===selectedStrategy)?.label
          }
          colorClass="neutral"
        />
        <StatCard
          title="Average Win"
          value={avgWin != null ? `${avgWin > 0 ? '+' : ''}${avgWin.toFixed(2)}%` : '--'}
          subtitle="Winning trades"
          colorClass={avgWin == null ? 'neutral' : avgWin >= 0 ? 'mint' : 'red'}
        />
        <StatCard
          title="Average Loss"
          value={avgLoss != null ? `${avgLoss > 0 ? '-' : ''}${Math.abs(avgLoss).toFixed(2)}%` : '--'}
          subtitle="Losing trades"
          colorClass={avgLoss == null ? 'neutral' : 'red'}
        />
        <StatCard
          title="Signal freshness (α)"
          value={
            status?.latest_signal_decay != null
              ? `${(Number(status.latest_signal_decay) * 100).toFixed(2)}%`
              : '--'
          }
          subtitle={
            status?.alpha_half_life_seconds != null
              ? `Half-life ${Math.round(Number(status.alpha_half_life_seconds) / 60)}m · veto below ${(Number(status.alpha_decay_veto_threshold ?? 0.5) * 100).toFixed(0)}%`
              : 'Last risk-check decay factor'
          }
          colorClass={
            status?.latest_signal_decay == null
              ? 'neutral'
              : Number(status.latest_signal_decay) >= Number(status?.alpha_decay_veto_threshold ?? 0.5)
                ? 'mint'
                : 'red'
          }
        />
      </div>

      {/* Equity Curve */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <Activity size={16} color="var(--color-mint)" />
          <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.9rem' }}>
            Equity Curve
          </span>
          {selectedStrategy !== 'global' && (
            <span className="pill mint" style={{ marginLeft: 4 }}>
              {STRATEGIES.find(s => s.value === selectedStrategy)?.label}
            </span>
          )}
        </div>
        <EquityChart data={equityCurve} />
      </div>

      {/* PnL Bar Chart */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <BarChart2 size={16} color="var(--color-mint)" />
          <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.9rem' }}>
            Daily PnL
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-faint)', marginLeft: 'auto' }}>
            <span className="mint">▪</span> Profit &nbsp;
            <span className="red">▪</span> Loss
          </span>
        </div>
        <PnLBarChart dailyPnl={dailyPnl} />
      </div>
    </div>
  );
}

export default DashboardPage;
