import React, { useState } from 'react';
import StatCard    from '../components/StatCard';
import EquityChart from '../components/EquityChart';
import PnLBarChart from '../components/PnLBarChart';
import { TrendingUp, TrendingDown, BarChart2, Target, Activity } from 'lucide-react';

const STRATEGIES = [
  { value: 'global',    label: 'All Strategies (Global)' },
  { value: 'ema',       label: 'EMA Crossover'           },
  { value: 'rsi',       label: 'RSI Scalper'             },
  { value: 'bollinger', label: 'Bollinger Bands'         },
  { value: 'trendline', label: 'Trendline Breakout'      },
  { value: 'macd',      label: 'MACD Momentum'           },
];

function fmt(v, suffix = '') {
  if (v == null) return '--';
  return `${v > 0 && suffix === '%' ? '+' : ''}${v}${suffix}`;
}

function DashboardPage({ analytics, status, balance }) {
  const [selectedStrategy, setSelectedStrategy] = useState('global');

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
  const initialCapital  = balance?.initial_capital ?? 10000;
  const balancePnlUsdt  = currentBalance != null ? currentBalance - initialCapital : null;
  const balancePnlPct   = currentBalance != null
    ? ((currentBalance - initialCapital) / initialCapital * 100).toFixed(2)
    : null;

  return (
    <div className="fade-in">
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

      {/* Stat Cards — 6 columns */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 14, marginBottom: 24 }}>
        {/* 1. Current Balance */}
        <StatCard
          title="Current Balance"
          value={currentBalance != null ? `$${currentBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '--'}
          subtitle={
            balancePnlUsdt != null
              ? `${balancePnlUsdt >= 0 ? '+' : ''}$${balancePnlUsdt.toFixed(2)} (${balancePnlPct >= 0 ? '+' : ''}${balancePnlPct}%)`
              : `Seed: $${initialCapital.toLocaleString()}`
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
          title="Avg Win / Loss"
          value={avgWin != null ? `${avgWin > 0 ? '+' : ''}${avgWin}%` : '--'}
          subtitle={avgLoss != null ? `Avg loss: ${avgLoss.toFixed(2)}%` : 'No data'}
          colorClass={avgWin == null ? 'neutral' : avgWin >= 0 ? 'mint' : 'red'}
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
