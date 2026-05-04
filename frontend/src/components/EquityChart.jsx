import React, { useState, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts';

const FILTERS = ['Day', 'Week', 'Month', 'All'];

const MINT      = '#00FFC2';
const MINT_DIM  = '#00d4a3';

function filterData(data, filter) {
  if (!data || data.length === 0) return [];
  if (filter === 'All') return data;

  const now   = new Date();
  const cutoff = new Date(now);
  if (filter === 'Day')   cutoff.setDate(now.getDate() - 1);
  if (filter === 'Week')  cutoff.setDate(now.getDate() - 7);
  if (filter === 'Month') cutoff.setMonth(now.getMonth() - 1);

  return data.filter(d => d.timestamp && new Date(d.timestamp) >= cutoff);
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div style={{
      background: 'rgba(10,15,30,0.95)',
      border: '1px solid rgba(0,255,194,0.2)',
      borderRadius: 10,
      padding: '10px 14px',
      fontSize: '0.75rem',
      lineHeight: 1.8
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 6 }}>
        {d?.timestamp ? new Date(d.timestamp).toLocaleString() : label}
      </div>
      <div style={{ color: MINT, fontWeight: 700 }}>
        Equity: {((d?.equity ?? 1) * 100 - 100).toFixed(3)}%
      </div>
      {d?.entry_price != null && (
        <div style={{ color: '#60a5fa' }}>Entry: ${d.entry_price.toFixed(2)}</div>
      )}
      {d?.exit_price != null && (
        <div style={{ color: '#f59e0b' }}>Exit: ${d.exit_price.toFixed(2)}</div>
      )}
      {d?.pnl != null && (
        <div style={{ color: d.pnl >= 0 ? MINT : '#FC5C65' }}>
          PnL: {(d.pnl * 100).toFixed(3)}%
        </div>
      )}
    </div>
  );
};

function EquityChart({ data }) {
  const [activeFilter, setActiveFilter] = useState('All');

  const chartData = useMemo(() => {
    const filtered = filterData(data, activeFilter);
    return filtered.map(d => ({
      ...d,
      equityPct: parseFloat(((d.equity - 1) * 100).toFixed(4)),
    }));
  }, [data, activeFilter]);

  if (!data || data.length === 0) {
    return (
      <div style={{
        height: 300,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        border: '1px dashed rgba(255,255,255,0.08)',
        borderRadius: 12,
        color: '#475569',
        fontSize: '0.875rem'
      }}>
        <span style={{ fontSize: '1.5rem' }}>📈</span>
        No equity data available — execute a trade to start tracking.
      </div>
    );
  }

  return (
    <div>
      {/* Filter Tabs */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <div className="time-filters">
          {FILTERS.map(f => (
            <button
              key={f}
              className={`time-filter-btn${activeFilter === f ? ' active' : ''}`}
              onClick={() => setActiveFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="mintGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={MINT} stopOpacity={0.25} />
                <stop offset="95%" stopColor={MINT} stopOpacity={0} />
              </linearGradient>
              <filter id="mintGlow">
                <feGaussianBlur stdDeviation="2" result="coloredBlur" />
                <feMerge>
                  <feMergeNode in="coloredBlur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />

            <XAxis
              dataKey="timestamp"
              stroke="transparent"
              tick={{ fill: '#475569', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
              interval="preserveStartEnd"
            />

            <YAxis
              stroke="transparent"
              tick={{ fill: '#475569', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `${v > 0 ? '+' : ''}${v}%`}
              domain={['auto', 'auto']}
              width={52}
            />

            <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" strokeDasharray="4 4" />

            <Tooltip content={<CustomTooltip />} />

            <Area
              type="monotone"
              dataKey="equityPct"
              stroke={MINT}
              strokeWidth={2}
              fill="url(#mintGrad)"
              dot={false}
              activeDot={{ r: 4, fill: MINT, stroke: 'none', filter: 'url(#mintGlow)' }}
              style={{ filter: 'drop-shadow(0 0 4px rgba(0,255,194,0.4))' }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default EquityChart;
