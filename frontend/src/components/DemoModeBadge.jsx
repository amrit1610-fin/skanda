import React from 'react';

/**
 * DemoModeBadge
 *
 * An unobtrusive, animated floating badge that appears whenever the frontend
 * cannot reach the backend WebSocket and has fallen back to Demo Mode.
 *
 * It renders absolutely in the top-right corner of the viewport, above the
 * sidebar's z-index but below modal overlays.
 *
 * Props:
 *   isVisible: boolean — controls render (still mounted when false for
 *              CSS transition smoothness, but hidden via opacity/transform)
 */
export default function DemoModeBadge({ isVisible }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={isVisible ? 'Demo mode active — backend engine offline' : ''}
      style={{
        // Positioning — floats at the top-right of the viewport
        position:   'fixed',
        top:        16,
        right:      20,
        zIndex:     300,

        // Visibility transition
        opacity:    isVisible ? 1 : 0,
        transform:  isVisible ? 'translateY(0)' : 'translateY(-8px)',
        pointerEvents: isVisible ? 'auto' : 'none',
        transition: 'opacity 0.35s ease, transform 0.35s ease',

        // Glassmorphism container
        display:        'flex',
        alignItems:     'center',
        gap:            8,
        padding:        '7px 14px 7px 10px',
        borderRadius:   999,
        background:     'rgba(15, 12, 8, 0.82)',
        border:         '1px solid rgba(251, 146, 60, 0.45)',
        boxShadow:      '0 0 18px rgba(251, 146, 60, 0.18), 0 2px 12px rgba(0,0,0,0.5)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        cursor:         'default',
        userSelect:     'none',
        whiteSpace:     'nowrap',
      }}
    >
      {/* Pulsing amber dot */}
      <span
        style={{
          width:        8,
          height:       8,
          borderRadius: '50%',
          background:   '#fb923c',
          boxShadow:    '0 0 8px #fb923c',
          flexShrink:   0,
          animation:    'demo-badge-pulse 2s ease-in-out infinite',
        }}
      />

      {/* Label */}
      <span
        style={{
          fontSize:      '0.72rem',
          fontWeight:    600,
          letterSpacing: '0.04em',
          color:         '#fdba74',
        }}
      >
        UI Demo Mode
      </span>

      {/* Separator */}
      <span
        style={{
          width:      1,
          height:     12,
          background: 'rgba(251,146,60,0.3)',
          flexShrink: 0,
        }}
      />

      {/* Sub-label */}
      <span
        style={{
          fontSize:  '0.68rem',
          color:     'rgba(253,186,116,0.7)',
          fontWeight: 500,
        }}
      >
        Backend Engine Offline
      </span>

      {/*
        Inline keyframes — avoids needing a separate CSS file update.
        The animation name is scoped uniquely to avoid conflicts.
      */}
      <style>{`
        @keyframes demo-badge-pulse {
          0%,100% { box-shadow: 0 0 5px #fb923c; opacity: 1; }
          50%      { box-shadow: 0 0 14px #fb923c, 0 0 24px rgba(251,146,60,0.4); opacity: 0.65; }
        }
      `}</style>
    </div>
  );
}
