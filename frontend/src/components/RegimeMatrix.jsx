import React from 'react';

// ── Constants ─────────────────────────────────────────────────────────────────
const TF_ORDER = ['1m', '5m', '15m', '1h', '4h', '1d'];

const TF_LABEL = {
  '1m':  '1M',
  '5m':  '5M',
  '15m': '15M',
  '1h':  '1H',
  '4h':  '4H',
  '1d':  '1D',
};

// Badge colours — map regime string → CSS token pair
const REGIME_STYLE = {
  STRONG_BULLISH: {
    bg:     'rgba(0,255,194,0.18)',
    border: 'rgba(0,255,194,0.55)',
    text:   '#00FFC2',
    dot:    '#00FFC2',
    glow:   'rgba(0,255,194,0.35)',
    label:  '↑↑ Strong Bull',
  },
  BULLISH: {
    bg:     'rgba(0,255,194,0.09)',
    border: 'rgba(0,255,194,0.30)',
    text:   '#7efce2',
    dot:    '#00FFC2',
    glow:   'rgba(0,255,194,0.15)',
    label:  '↑ Bullish',
  },
  SIDEWAYS: {
    bg:     'rgba(148,163,184,0.12)',
    border: 'rgba(148,163,184,0.30)',
    text:   '#94a3b8',
    dot:    '#94a3b8',
    glow:   'transparent',
    label:  '─ Sideways',
  },
  BEARISH: {
    bg:     'rgba(252,92,101,0.09)',
    border: 'rgba(252,92,101,0.30)',
    text:   '#fca5a5',
    dot:    '#FC5C65',
    glow:   'rgba(252,92,101,0.15)',
    label:  '↓ Bearish',
  },
  STRONG_BEARISH: {
    bg:     'rgba(252,92,101,0.18)',
    border: 'rgba(252,92,101,0.55)',
    text:   '#FC5C65',
    dot:    '#FC5C65',
    glow:   'rgba(252,92,101,0.35)',
    label:  '↓↓ Strong Bear',
  },
  UNKNOWN: {
    bg:     'rgba(148,163,184,0.08)',
    border: 'rgba(148,163,184,0.18)',
    text:   '#64748b',
    dot:    '#475569',
    glow:   'transparent',
    label:  '? Unknown',
  },
};

// Score → display colour for the macro score number
function scoreColor(score) {
  if (score >=  0.5) return '#00FFC2';
  if (score >=  0.15) return '#7efce2';
  if (score <= -0.5) return '#FC5C65';
  if (score <= -0.15) return '#fca5a5';
  return '#94a3b8';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TimeframeBadge({ tf, regime }) {
  const style = REGIME_STYLE[regime] ?? REGIME_STYLE.UNKNOWN;

  return (
    <div
      style={{
        display:       'flex',
        flexDirection: 'column',
        alignItems:    'center',
        gap:           4,
        padding:       '8px 10px',
        borderRadius:  8,
        background:    style.bg,
        border:        `1px solid ${style.border}`,
        boxShadow:     `0 0 10px ${style.glow}`,
        minWidth:      60,
        transition:    'box-shadow 0.25s ease',
      }}
    >
      {/* Timeframe label */}
      <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-faint)', letterSpacing: '0.08em' }}>
        {TF_LABEL[tf] ?? tf.toUpperCase()}
      </span>

      {/* Regime indicator dot */}
      <span
        style={{
          width:        8,
          height:       8,
          borderRadius: '50%',
          background:   style.dot,
          boxShadow:    `0 0 6px ${style.dot}`,
          display:      'block',
        }}
      />

      {/* Regime text */}
      <span style={{ fontSize: '0.65rem', color: style.text, textAlign: 'center', lineHeight: 1.25 }}>
        {style.label}
      </span>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

/**
 * RegimeMatrix
 *
 * Props:
 *   economistData: {
 *     mtf_matrix:          { "1m": "BULLISH", "5m": "SIDEWAYS", ... },
 *     overall_macro_score: 0.42,
 *     dominant_regime:     "BULLISH",
 *     regime_name:         "Trend Breakout",
 *     confidence_pct:      87.3,
 *   }
 */
export default function RegimeMatrix({ economistData }) {
  const matrix        = economistData?.mtf_matrix         ?? {};
  const macroScore    = economistData?.overall_macro_score ?? null;
  const dominant      = economistData?.dominant_regime     ?? 'UNKNOWN';
  const domStyle      = REGIME_STYLE[dominant]             ?? REGIME_STYLE.UNKNOWN;
  const hasData       = Object.keys(matrix).length > 0;

  return (
    <div
      className="card"
      style={{
        marginBottom: 20,
        borderColor:  domStyle.border,
        boxShadow:    `0 0 0 1px ${domStyle.border}, 0 0 24px ${domStyle.glow}`,
        background:   'linear-gradient(120deg, rgba(17,24,39,0.96) 0%, rgba(9,14,24,0.99) 100%)',
      }}
      role="region"
      aria-label="Multi-Timeframe Regime Matrix"
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: '0.7rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-faint)', marginBottom: 4 }}>
            MTF Regime Radar
          </div>
          <div style={{ fontSize: '1.05rem', fontWeight: 700, color: domStyle.text }}>
            {dominant.replace('_', ' ')}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 2 }}>
            EMA20 / EMA50 / SMA200 stack · 6 timeframes
          </div>
        </div>

        {/* Macro Score Gauge */}
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
            MACRO SCORE
          </div>
          {macroScore !== null ? (
            <>
              <div
                style={{
                  fontSize:   '1.6rem',
                  fontWeight:  800,
                  color:       scoreColor(macroScore),
                  textShadow: `0 0 12px ${scoreColor(macroScore)}55`,
                  lineHeight:  1,
                }}
              >
                {macroScore >= 0 ? '+' : ''}{macroScore.toFixed(2)}
              </div>
              {/* Score bar */}
              <div style={{ marginTop: 6, width: 120, height: 5, borderRadius: 4, background: 'rgba(255,255,255,0.08)', overflow: 'hidden', marginLeft: 'auto' }}>
                <div
                  style={{
                    height:       '100%',
                    width:        `${Math.abs(macroScore) * 50}%`,
                    marginLeft:   macroScore >= 0 ? '50%' : `${(1 + macroScore) * 50}%`,
                    background:   scoreColor(macroScore),
                    borderRadius: 4,
                    transition:   'width 0.4s ease, margin-left 0.4s ease',
                  }}
                />
              </div>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-faint)', marginTop: 3 }}>
                -1.0 (Bear)  ←  →  +1.0 (Bull)
              </div>
            </>
          ) : (
            <div style={{ fontSize: '1.1rem', color: 'var(--text-faint)' }}>--</div>
          )}
        </div>
      </div>

      {/* Timeframe Badge Grid */}
      {hasData ? (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {TF_ORDER.map((tf) => (
            <TimeframeBadge
              key={tf}
              tf={tf}
              regime={matrix[tf] ?? 'UNKNOWN'}
            />
          ))}
        </div>
      ) : (
        <div style={{ color: 'var(--text-faint)', fontSize: '0.82rem', padding: '8px 0' }}>
          Waiting for live data — MTF radar will populate on the next trading cycle.
        </div>
      )}

      {/* Veto Rule Footer */}
      <div style={{ marginTop: 14, padding: '8px 12px', borderRadius: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-faint)' }}>
          <span style={{ color: '#FC5C65' }}>■</span>&nbsp;Risk Manager veto fires when score&nbsp;
          <code style={{ color: '#fca5a5' }}>&lt; −0.5</code>&nbsp;(BUY into Bear) or&nbsp;
          <code style={{ color: '#7efce2' }}>&gt; +0.5</code>&nbsp;(SELL into Bull).&nbsp;
          Higher timeframes (4h, 1d) carry more authority.
        </span>
      </div>
    </div>
  );
}
