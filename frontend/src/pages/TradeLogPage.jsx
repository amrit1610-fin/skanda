import React, { useState, useMemo } from 'react';
import {
  ArrowUpDown, ArrowUp, ArrowDown, ChevronLeft, ChevronRight,
  TrendingUp, TrendingDown, Minus
} from 'lucide-react';

const PAGE_SIZE = 20;

const STRATEGY_LABELS = {
  ema_8_30:        '8/30 EMA Momentum',
  ema_9_15:        '9/15 EMA Scalping',
  trendline_break: 'Multi-TF Trendline Break',
  unknown:    'Unknown',
};

const COLUMNS = [
  { key: 'timestamp',     label: 'Date / Time'  },
  { key: 'symbol',        label: 'Symbol'       },
  { key: 'quantity',      label: 'Qty'          },
  { key: 'strategy_used', label: 'Strategy'     },
  { key: 'side',          label: 'Side'         },   // NEW
  { key: 'decay_factor',  label: 'α decay'      },
  { key: 'entry_price',   label: 'Entry'        },
  { key: 'exit_price',    label: 'Exit'         },
  { key: 'pnl',           label: 'PnL %'        },
];

function SortIcon({ col, sortKey, sortDir }) {
  if (col !== sortKey) return <ArrowUpDown size={11} style={{ opacity: 0.3, marginLeft: 4 }} />;
  return sortDir === 'asc'
    ? <ArrowUp   size={11} color="var(--color-mint)" style={{ marginLeft: 4 }} />
    : <ArrowDown size={11} color="var(--color-mint)" style={{ marginLeft: 4 }} />;
}

function SideCell({ side }) {
  if (!side) return <span style={{ color: 'var(--text-faint)' }}>--</span>;
  const isLong  = side === 'LONG';
  const isShort = side === 'SHORT';
  return (
    <span style={{
      display:     'inline-flex',
      alignItems:  'center',
      gap:         5,
      fontWeight:  700,
      fontSize:    '0.8rem',
      color:       isLong ? 'var(--color-mint)' : isShort ? 'var(--color-red)' : 'var(--text-muted)',
      letterSpacing: '0.04em',
    }}>
      {isLong  && <TrendingUp   size={13} />}
      {isShort && <TrendingDown size={13} />}
      {!isLong && !isShort && <Minus size={13} />}
      {side}
    </span>
  );
}

function TradeLogPage({ logs }) {
  const [sortKey, setSortKey] = useState('timestamp');
  const [sortDir, setSortDir] = useState('desc');
  const [page,    setPage]    = useState(0);

  // ── Filter: only executed trades ──────────────────────────────────────────
  const executed = useMemo(
    () => (logs ?? []).filter(r => r.status === 'executed'),
    [logs]
  );

  const sorted = useMemo(() => {
    return [...executed].sort((a, b) => {
      let av = a[sortKey] ?? '';
      let bv = b[sortKey] ?? '';
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }, [executed, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageRows   = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSort = (col) => {
    if (col === sortKey) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(col); setSortDir('desc'); }
    setPage(0);
  };

  const fmtDate = (ts) => {
    if (!ts) return '--';
    try {
      return new Date(ts).toLocaleString('en-IN', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    } catch { return ts; }
  };

  const fmtPrice = (p) =>
    p != null ? `$${Number(p).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '--';

  const totalVetoed = (logs ?? []).length - executed.length;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Trade Log</h1>
          <p className="page-subtitle">
            {executed.length} executed trades
            {totalVetoed > 0 && (
              <span style={{ color: 'var(--text-faint)', marginLeft: 8 }}>
                · {totalVetoed} vetoed (hidden)
              </span>
            )}
          </p>
        </div>
      </div>

      <div className="trade-table-wrapper">
        <table className="trade-table">
          <thead>
            <tr>
              {COLUMNS.map(col => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={sortKey === col.key ? 'sorted' : ''}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                    {col.label}
                    <SortIcon col={col.key} sortKey={sortKey} sortDir={sortDir} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} style={{
                  textAlign: 'center', padding: '48px 0',
                  color: 'var(--text-faint)',
                }}>
                  <div style={{ fontSize: '1.8rem', marginBottom: 10 }}>📭</div>
                  No executed trades yet — the system is running and evaluating signals.
                </td>
              </tr>
            ) : (
              pageRows.map((row, i) => {
                const pnl      = row.pnl ?? null;
                const isProfit = pnl != null && pnl > 0;
                const isLoss   = pnl != null && pnl < 0;
                const side     = row.side ?? (
                  row.signal_type === 'BUY'  ? 'LONG'  :
                  row.signal_type === 'SELL' ? 'SHORT' : null
                );

                return (
                  <tr key={i}>
                    {/* Date */}
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                      {fmtDate(row.timestamp)}
                    </td>

                    {/* Symbol */}
                    <td>
                      <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {row.symbol ?? 'BTCUSDT'}
                      </span>
                    </td>

                    {/* Quantity */}
                    <td style={{ color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '0.82rem' }}>
                      {row.quantity != null ? Number(row.quantity).toFixed(6) : '--'}
                    </td>

                    {/* Strategy */}
                    <td>
                      <span className="pill muted">
                        {STRATEGY_LABELS[row.strategy_used] ?? row.strategy_used ?? '--'}
                      </span>
                    </td>

                    {/* Side — LONG / SHORT */}
                    <td>
                      <SideCell side={side} />
                    </td>

                    {/* Alpha decay at approval */}
                    <td style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                      {row.decay_factor != null
                        ? `${(Number(row.decay_factor) * 100).toFixed(1)}%`
                        : <span style={{ color: 'var(--text-faint)' }}>--</span>}
                    </td>

                    {/* Entry Price */}
                    <td style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                      {fmtPrice(row.entry_price)}
                    </td>

                    {/* Exit Price */}
                    <td style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                      {fmtPrice(row.exit_price)}
                    </td>

                    {/* PnL % */}
                    <td>
                      {pnl != null ? (
                        <span style={{
                          color:      isProfit ? 'var(--color-mint)' : isLoss ? 'var(--color-red)' : 'var(--text-muted)',
                          fontWeight: 700,
                          fontFamily: 'monospace',
                        }}>
                          {isProfit ? '+' : ''}{(pnl * 100).toFixed(3)}%
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-faint)' }}>--</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
          gap: 12, marginTop: 16, fontSize: '0.8rem', color: 'var(--text-muted)'
        }}>
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '5px 10px',
              cursor: page === 0 ? 'not-allowed' : 'pointer',
              color: page === 0 ? 'var(--text-faint)' : 'var(--text-primary)',
              display: 'flex', alignItems: 'center'
            }}
          >
            <ChevronLeft size={14} />
          </button>
          <span>Page {page + 1} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '5px 10px',
              cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer',
              color: page >= totalPages - 1 ? 'var(--text-faint)' : 'var(--text-primary)',
              display: 'flex', alignItems: 'center'
            }}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

export default TradeLogPage;
