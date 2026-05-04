import React, { useEffect, useState, useRef } from 'react';
import { Terminal, ChevronDown, ChevronUp, X } from 'lucide-react';

function AgentConsole() {
  const [logs, setLogs]           = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [visible, setVisible]     = useState(true);
  const bottomRef                 = useRef(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/api/stream');

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLogs(prev => [...prev, data].slice(-150));
      } catch {
        // raw text
        if (event.data?.trim()) {
          setLogs(prev => [...prev, { message: event.data, timestamp: new Date().toISOString() }].slice(-150));
        }
      }
    };

    ws.onerror = () => {};

    return () => ws.close();
  }, []);

  useEffect(() => {
    if (!collapsed) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, collapsed]);

  if (!visible) return null;

  const getLogColor = (log) => {
    if (log.type === 'action') return '#00FFC2';
    if (log.type === 'error')  return '#FC5C65';
    if (log.agent)             return '#60a5fa';
    return '#94a3b8';
  };

  return (
    <div className={`agent-console-overlay${collapsed ? ' collapsed' : ''}`}>
      {/* Header / toggle bar */}
      <div className="console-header" onClick={() => setCollapsed(c => !c)}>
        <div className="title">
          <Terminal size={13} />
          agent_stream.log
          {logs.length > 0 && (
            <span style={{
              background: 'rgba(0,255,194,0.15)',
              color: '#00FFC2',
              fontSize: '0.6rem',
              padding: '1px 6px',
              borderRadius: '99px',
              marginLeft: 4
            }}>
              {logs.length}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {collapsed
            ? <ChevronUp size={14} color="#94a3b8" />
            : <ChevronDown size={14} color="#94a3b8" />
          }
          <button
            onClick={(e) => { e.stopPropagation(); setVisible(false); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}
          >
            <X size={13} color="#94a3b8" />
          </button>
        </div>
      </div>

      {/* Log body */}
      <div className={`console-body${collapsed ? ' hidden' : ''}`}>
        {logs.length === 0 ? (
          <span style={{ color: '#475569', fontStyle: 'italic' }}>
            Waiting for agent activity...
          </span>
        ) : (
          logs.map((log, i) => (
            <div key={i} style={{ marginBottom: 4 }}>
              <span style={{ color: '#475569' }}>
                [{log.timestamp?.split('T')[1]?.split('.')[0] ?? '??:??:??'}]
              </span>{' '}
              {log.agent && (
                <span style={{ color: '#60a5fa', fontWeight: 700 }}>[{log.agent}]</span>
              )}{' '}
              <span style={{ color: getLogColor(log) }}>
                {log.message || JSON.stringify(log)}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

export default AgentConsole;
