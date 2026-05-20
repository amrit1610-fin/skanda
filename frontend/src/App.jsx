import { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import Sidebar       from './components/Sidebar';
import AgentConsole  from './components/AgentConsole';
import DashboardPage from './pages/DashboardPage';
import TradeLogPage  from './pages/TradeLogPage';
import CalendarPage  from './pages/CalendarPage';
import SettingsPage  from './pages/SettingsPage';
import BacktestPage  from './pages/BacktestPage';
import DemoModeBadge from './components/DemoModeBadge';
import {
  MOCK_BALANCE,
  MOCK_STATUS,
  MOCK_ANALYTICS,
  MOCK_LOGS,
  MOCK_ECONOMIST_BASE,
  tickedEconomistData,
} from './utils/mockData';
import './App.css';

// ── Config ────────────────────────────────────────────────────────────────────
const API_BASE  = 'http://localhost:8000/api';
const WS_URL    = 'ws://localhost:8000/api/stream';

// Demo tick interval: economist data + price drift updates every N ms
const DEMO_TICK_MS = 4000;

// How long to wait for a WS connection before deciding we're in demo mode (ms)
const WS_CONNECT_TIMEOUT_MS = 3500;

// ── App ───────────────────────────────────────────────────────────────────────

function App() {
  const [activePage,    setActivePage]    = useState('dashboard');
  const [status,        setStatus]        = useState(null);
  const [analytics,     setAnalytics]     = useState(null);
  const [logs,          setLogs]          = useState([]);
  const [balance,       setBalance]       = useState(null);
  const [isLive,        setIsLive]        = useState(false);
  const [tradingMode,   setTradingMode]   = useState('paper');
  const [economistData, setEconomistData] = useState(null);
  const [systemMode,    setSystemMode]    = useState('auto');

  // ── Demo mode state ────────────────────────────────────────────────────────
  const [isDemoMode,    setIsDemoMode]    = useState(false);

  // Ref to the current economist base so the ticker can drift from live data
  const economistRef = useRef(MOCK_ECONOMIST_BASE);

  // ── REST polling (live) ────────────────────────────────────────────────────
  const fetchData = async () => {
    try {
      const [statusRes, analyticsRes, logsRes, balanceRes] = await Promise.all([
        axios.get(`${API_BASE}/status`),
        axios.get(`${API_BASE}/analytics`),
        axios.get(`${API_BASE}/logs`),
        axios.get(`${API_BASE}/balance`),
      ]);
      setStatus(statusRes.data);
      setAnalytics(analyticsRes.data);
      setLogs(logsRes.data);
      setBalance(balanceRes.data);
      setIsLive(statusRes.data?.online === true);
    } catch {
      setIsLive(false);
    }
  };

  // ── Demo mode: seed all state from mock data ───────────────────────────────
  const activateDemoMode = () => {
    setIsDemoMode(true);
    setStatus(MOCK_STATUS);
    setAnalytics(MOCK_ANALYTICS);
    setLogs(MOCK_LOGS);
    setBalance(MOCK_BALANCE);
    setIsLive(false);
    setEconomistData(MOCK_ECONOMIST_BASE);
    economistRef.current = MOCK_ECONOMIST_BASE;
  };

  // ── WebSocket with timeout-based demo fallback ─────────────────────────────
  useEffect(() => {
    let ws = null;
    let timeoutId = null;
    let demoTickerId = null;
    let didConnect = false;
    let isDestroyed = false;

    const startDemoTicker = () => {
      // Tick economist data every DEMO_TICK_MS so the Regime Radar animates
      demoTickerId = setInterval(() => {
        const next = tickedEconomistData(economistRef.current);
        economistRef.current = next;
        setEconomistData({ ...next });
      }, DEMO_TICK_MS);
    };

    const tryConnect = () => {
      try {
        ws = new WebSocket(WS_URL);
      } catch {
        // WebSocket constructor itself threw (e.g. invalid URL in some browsers)
        activateDemoMode();
        startDemoTicker();
        return;
      }

      // If WS doesn't open within the timeout window, switch to demo mode
      timeoutId = setTimeout(() => {
        if (!didConnect && !isDestroyed) {
          ws?.close();
          activateDemoMode();
          startDemoTicker();
        }
      }, WS_CONNECT_TIMEOUT_MS);

      ws.onopen = () => {
        if (isDestroyed) return;
        didConnect = true;
        clearTimeout(timeoutId);
        // Connection succeeded — ensure we're out of demo mode
        setIsDemoMode(false);
      };

      ws.onmessage = (event) => {
        if (isDestroyed) return;
        try {
          const parsed = JSON.parse(event.data);
          if (parsed?.economist_data) {
            setEconomistData(parsed.economist_data);
            economistRef.current = parsed.economist_data;
          }
        } catch {
          // non-JSON frames are fine — ignore
        }
      };

      ws.onerror = () => {
        // onerror fires before onclose; onclose will clean up
      };

      ws.onclose = () => {
        if (isDestroyed) return;
        clearTimeout(timeoutId);
        if (!didConnect) {
          // Connection refused / immediately closed — go to demo mode
          activateDemoMode();
          startDemoTicker();
        }
        // If it was previously connected but dropped, we keep the last state
        // visible and the existing REST polling will mark isLive = false
      };
    };

    tryConnect();

    return () => {
      isDestroyed = true;
      clearTimeout(timeoutId);
      clearInterval(demoTickerId);
      ws?.close();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Live REST polling (skipped in demo mode to avoid console errors) ───────
  useEffect(() => {
    if (isDemoMode) return; // Don't hammer a dead server every 5s
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [isDemoMode]);

  const activeStrategy = status?.strategy ?? null;

  return (
    <div
      className={`app-shell ${tradingMode === 'real'
        ? 'border-4 border-red-600 shadow-[0_0_15px_rgba(220,38,38,0.5)]'
        : ''}`}
    >
      {/* Demo Mode Badge — floats in top-right of the sidebar area */}
      <DemoModeBadge isVisible={isDemoMode} />

      {/* Fixed Sidebar */}
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        activeStrategy={activeStrategy}
        isLive={isLive}
        systemMode={systemMode}
        isDemoMode={isDemoMode}
        onStrategyChange={fetchData}
      />

      {/* Scrollable main area */}
      <main className="main-content" style={{ marginLeft: 'var(--sidebar-width)' }}>
        {activePage === 'dashboard' && (
          <DashboardPage
            analytics={analytics}
            status={status}
            balance={balance}
            economistData={economistData}
            tradingMode={tradingMode}
            onToggleMode={setTradingMode}
            systemMode={systemMode}
            setSystemMode={setSystemMode}
            onStrategyChange={isDemoMode ? () => {} : fetchData}
            isDemoMode={isDemoMode}
          />
        )}
        {activePage === 'tradelog' && (
          <TradeLogPage logs={logs} isDemoMode={isDemoMode} />
        )}
        {activePage === 'calendar' && (
          <CalendarPage analytics={analytics} />
        )}
        {activePage === 'settings' && (
          <SettingsPage status={status} onSaved={isDemoMode ? () => {} : fetchData} />
        )}
        {activePage === 'backtest' && <BacktestPage />}
      </main>

      {/* Glassmorphism Agent Console Overlay */}
      <AgentConsole />
    </div>
  );
}

export default App;
