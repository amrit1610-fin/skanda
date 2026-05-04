import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

function StatCard({ title, value, subtitle, colorClass = 'neutral', mini, showPie = false, pieValue }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{title}</span>

      {showPie && pieValue !== undefined ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className={`stat-value ${colorClass}`} style={{ minWidth: 0 }}>
            {value}
          </span>
          <div style={{ width: 64, height: 64, flexShrink: 0 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={[
                    { name: 'Win',  value: pieValue },
                    { name: 'Loss', value: 100 - pieValue },
                  ]}
                  cx="50%"
                  cy="50%"
                  innerRadius={20}
                  outerRadius={30}
                  startAngle={90}
                  endAngle={-270}
                  dataKey="value"
                  strokeWidth={0}
                >
                  <Cell fill="#00FFC2" />
                  <Cell fill="#FC5C65" />
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: 'rgba(10,15,30,0.95)',
                    border: '1px solid rgba(0,255,194,0.2)',
                    borderRadius: 8,
                    fontSize: '0.7rem'
                  }}
                  formatter={(v, n) => [`${v.toFixed(1)}%`, n]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <span className={`stat-value ${colorClass}`}>{value}</span>
      )}

      {subtitle && <span className="stat-sub">{subtitle}</span>}
    </div>
  );
}

export default StatCard;
