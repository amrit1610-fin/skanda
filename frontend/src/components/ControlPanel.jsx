import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Settings2 } from 'lucide-react';

function ControlPanel({ currentStatus, onUpdate }) {
  const [strategy, setStrategy] = useState('ema');
  const [interval, setIntervalVal] = useState(3600);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (currentStatus) {
      setStrategy(currentStatus.strategy || 'ema');
      setIntervalVal(currentStatus.interval_seconds || 3600);
    }
  }, [currentStatus]);

  const handleSave = async () => {
    setLoading(true);
    try {
      await axios.post('http://localhost:8000/api/switch-strategy', {
        strategy,
        interval_seconds: parseInt(interval)
      });
      if (onUpdate) onUpdate();
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <h3 className="flex items-center gap-2 text-white font-medium mb-4">
        <Settings2 size={18} className="text-blue-400" /> System Controls
      </h3>
      
      <div className="space-y-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Active Strategy</label>
          <select 
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="ema">EMA Crossover</option>
            <option value="rsi">RSI Scalper</option>
            <option value="bollinger">Bollinger Bands</option>
            <option value="trendline">Trendline Breakout</option>
            <option value="macd">MACD Momentum</option>
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Loop Interval (Seconds)</label>
          <input 
            type="number"
            min="60"
            value={interval}
            onChange={(e) => setIntervalVal(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          />
        </div>

        <button 
          onClick={handleSave}
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2 rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? 'Applying...' : 'Apply Configuration'}
        </button>
      </div>
    </div>
  );
}

export default ControlPanel;
