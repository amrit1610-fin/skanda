import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, ReferenceLine
} from 'recharts';

const MINT = '#00FFC2';
const RED  = '#FC5C65';

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value ?? 0;
  return (
    <div style={{
      background: 'rgba(10,15,30,0.95)',
      border: `1px solid ${val >= 0 ? 'rgba(0,255,194,0.2)' : 'rgba(252,92,101,0.2)'}`,
      borderRadius: 10,
      padding: '9px 13px',
      fontSize: '0.75rem',
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 4 }}>{payload[0]?.payload?.date}</div>
      <div style={{ color: val >= 0 ? MINT : RED, fontWeight: 700 }}>
        PnL: {val >= 0 ? '+' : ''}{(val * 100).toFixed(3)}%
      </div>
    </div>
  );
};

function PnLBarChart({ dailyPnl }) {
  const chartData = useMemo(() => {
    if (!dailyPnl || Object.keys(dailyPnl).length === 0) return [];
    return Object.entries(dailyPnl)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, pnl]) => ({
        date,
        pnl: parseFloat(pnl.toFixed(6)),
      }));
  }, [dailyPnl]);

  if (!chartData.length) {
    return (
      <div style={{
        height: 220,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#475569',
        fontSize: '0.875rem',
        border: '1px dashed rgba(255,255,255,0.08)',
        borderRadius: 12,
      }}>
        No daily PnL data yet.
      </div>
    );
  }

  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 6, right: 4, left: 0, bottom: 0 }} barSize={18}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="date"
            stroke="transparent"
            tick={{ fill: '#475569', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => v.slice(5)} // MM-DD
            interval="preserveStartEnd"
          />
          <YAxis
            stroke="transparent"
            tick={{ fill: '#475569', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`}
            width={56}
          />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.pnl >= 0 ? MINT : RED} opacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PnLBarChart;
