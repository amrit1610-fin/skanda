import React from 'react';
import {
  LayoutDashboard, ClipboardList, CalendarDays,
  Zap, SlidersHorizontal, FlaskConical
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'tradelog', label: 'Trade Log', icon: ClipboardList },
  { id: 'calendar', label: 'Calendar', icon: CalendarDays },
  { id: 'backtest', label: 'Backtest', icon: FlaskConical },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal },
];

function Sidebar({ activePage, onNavigate, isLive, systemMode, isDemoMode }) {
  return (
    <aside className="sidebar" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* ── Logo ────────────────────────────────── */}
      <div className="sidebar-logo">
        <h2>
          <Zap size={24} className="logo-icon" />
          SKANDA
        </h2>
        <p>The Ultimate HUNT FOR ALPHA </p>
      </div>

      {/* ── Navigation ──────────────────────────── */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isSettingsDisabled = id === 'settings' && systemMode === 'auto';
          return (
            <button
              key={id}
              className={`nav-item${activePage === id ? ' active' : ''} ${isSettingsDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              onClick={() => !isSettingsDisabled && onNavigate(id)}
              disabled={isSettingsDisabled}
              title={isSettingsDisabled ? 'Settings are disabled while AI Auto-Pilot is active' : ''}
            >
              <Icon size={17} />
              {label}
            </button>
          );
        })}
      </nav>

      {/* ── Footer: connection status ────────────── */}
      <div className="sidebar-footer" style={{ marginTop: 'auto' }}>
        {isDemoMode ? (
          /* Amber Demo Mode indicator */
          <div
            className="live-indicator"
            style={{ color: '#fb923c' }}
          >
            <span
              className="pulse-dot"
              style={{
                background: '#fb923c',
                boxShadow:  '0 0 6px #fb923c',
                animation:  'demo-badge-pulse 2s ease-in-out infinite',
              }}
            />
            Demo Mode
          </div>
        ) : (
          <div className={`live-indicator${isLive ? ' online' : ' offline'}`}>
            <span className={`pulse-dot${isLive ? '' : ' red'}`} />
            {isLive ? 'System Live' : 'Backend Offline'}
          </div>
        )}
      </div>
    </aside>
  );
}

export default Sidebar;

