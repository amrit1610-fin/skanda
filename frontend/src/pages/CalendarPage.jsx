import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function buildCalendarDays(year, month) {
  // Returns array of { date: Date | null } for grid cells
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];

  // Leading empty cells
  for (let i = 0; i < firstDay; i++) cells.push(null);

  // Day cells
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(new Date(year, month, d));
  }

  return cells;
}

function formatKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function CalendarPage({ analytics }) {
  const now = new Date();
  const [viewYear,  setViewYear]  = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth());

  // Merge global daily_pnl map
  const dailyPnl = analytics?.global_metrics?.daily_pnl ?? {};

  const cells = useMemo(() => buildCalendarDays(viewYear, viewMonth), [viewYear, viewMonth]);

  const todayKey = formatKey(now);

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };

  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  const monthLabel = new Date(viewYear, viewMonth, 1).toLocaleString('en-US', {
    month: 'long', year: 'numeric'
  });

  // Compute summary stats for the visible month
  const monthStats = useMemo(() => {
    let profit = 0, loss = 0, total = 0;
    cells.forEach(d => {
      if (!d) return;
      const key = formatKey(d);
      const pnl = dailyPnl[key];
      if (pnl == null) return;
      total += pnl;
      if (pnl > 0) profit++;
      else if (pnl < 0) loss++;
    });
    return { total, profit, loss };
  }, [cells, dailyPnl]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Calendar</h1>
          <p className="page-subtitle">Daily PnL heatmap — green profit days, red loss days</p>
        </div>

        {/* Month stats */}
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-faint)' }}>Month PnL</div>
            <div style={{
              fontSize: '1rem', fontWeight: 700,
              color: monthStats.total >= 0 ? 'var(--color-mint)' : 'var(--color-red)'
            }}>
              {monthStats.total >= 0 ? '+' : ''}{(monthStats.total * 100).toFixed(2)}%
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-faint)' }}>Profit Days</div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--color-mint)' }}>{monthStats.profit}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-faint)' }}>Loss Days</div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--color-red)' }}>{monthStats.loss}</div>
          </div>
        </div>
      </div>

      <div className="card">
        {/* Month Navigator */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <button
            onClick={prevMonth}
            style={{
              background: 'var(--bg-surface-2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '7px 10px', cursor: 'pointer',
              color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
              transition: 'color 0.15s'
            }}
          >
            <ChevronLeft size={16} />
          </button>

          <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
            {monthLabel}
          </span>

          <button
            onClick={nextMonth}
            style={{
              background: 'var(--bg-surface-2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '7px 10px', cursor: 'pointer',
              color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
            }}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* Day-of-week headers */}
        <div className="calendar-grid">
          {DAY_LABELS.map(d => (
            <div key={d} className="cal-day-header">{d}</div>
          ))}
        </div>

        {/* Calendar cells */}
        <div className="calendar-grid" style={{ marginTop: 4 }}>
          {cells.map((date, i) => {
            if (!date) {
              return <div key={`empty-${i}`} className="cal-day empty" />;
            }

            const key    = formatKey(date);
            const pnl    = dailyPnl[key];
            const isToday = key === todayKey;

            let dayClass = 'cal-day neutral';
            if (pnl != null && pnl > 0)  dayClass = 'cal-day profit';
            if (pnl != null && pnl < 0)  dayClass = 'cal-day loss';
            if (isToday)                  dayClass += ' today';

            return (
              <div key={key} className={dayClass} title={pnl != null ? `PnL: ${(pnl*100).toFixed(3)}%` : 'No trades'}>
                <span className="cal-day-num">{date.getDate()}</span>
                {pnl != null && (
                  <span className="cal-day-pnl">
                    {pnl > 0 ? '+' : ''}{(pnl * 100).toFixed(1)}%
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Legend */}
        <div style={{
          display: 'flex', gap: 20, marginTop: 24, paddingTop: 16,
          borderTop: '1px solid var(--border)', fontSize: '0.72rem', color: 'var(--text-faint)'
        }}>
          <span><span style={{ color: 'var(--color-mint)' }}>■</span> Profit day</span>
          <span><span style={{ color: 'var(--color-red)'  }}>■</span> Loss day</span>
          <span><span style={{ color: 'var(--text-faint)' }}>■</span> No trades</span>
          <span><span style={{ color: 'var(--color-mint)', textDecoration: 'underline' }}>■</span> Today</span>
        </div>
      </div>
    </div>
  );
}

export default CalendarPage;
