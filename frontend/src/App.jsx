import { useEffect, useState } from 'react';
import axios from 'axios';
import Sidebar       from './components/Sidebar';
import AgentConsole  from './components/AgentConsole';
import DashboardPage from './pages/DashboardPage';
import TradeLogPage  from './pages/TradeLogPage';
import CalendarPage  from './pages/CalendarPage';
import SettingsPage  from './pages/SettingsPage';
import BacktestPage  from './pages/BacktestPage';
import './App.css';

const API_BASE = 'http://localhost:8000/api';

function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const [status,     setStatus]     = useState(null);
  const [analytics,  setAnalytics]  = useState(null);
  const [logs,       setLogs]       = useState([]);
  const [balance,    setBalance]    = useState(null);
  const [isLive,     setIsLive]     = useState(false);

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
      // Mark live only when status has the 'online' flag we now inject
      setIsLive(statusRes.data?.online === true);
    } catch {
      setIsLive(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const activeStrategy = status?.strategy ?? null;

  return (
    <div className="app-shell">
      {/* Fixed Sidebar */}
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        activeStrategy={activeStrategy}
        isLive={isLive}
        onStrategyChange={fetchData}
      />

      {/* Scrollable main area (offset by sidebar width) */}
      <main className="main-content" style={{ marginLeft: 'var(--sidebar-width)' }}>
        {activePage === 'dashboard' && (
          <DashboardPage analytics={analytics} status={status} balance={balance} />
        )}
        {activePage === 'tradelog' && (
          <TradeLogPage logs={logs} />
        )}
        {activePage === 'calendar' && (
          <CalendarPage analytics={analytics} />
        )}
        {activePage === 'settings' && (
          <SettingsPage status={status} onSaved={fetchData} />
        )}
        {activePage === 'backtest' && (
          <BacktestPage />
        )}
      </main>

      {/* Glassmorphism Agent Console Overlay */}
      <AgentConsole />
    </div>
  );
}

export default App;
