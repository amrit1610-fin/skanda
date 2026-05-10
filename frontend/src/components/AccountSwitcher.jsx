import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

const AccountSwitcher = ({ tradingMode, onToggleMode }) => {
  const [showModal, setShowModal] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectChange = (selectedMode) => {
    setIsDropdownOpen(false);
    if (selectedMode === tradingMode) return;

    if (selectedMode === 'real') {
      setShowModal(true);
    } else {
      executeToggle('paper');
    }
  };

  const executeToggle = async (modeToSet) => {
    try {
      const isPaper = modeToSet === 'paper';
      const response = await fetch('http://localhost:8000/api/toggle-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_paper: isPaper }),
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        onToggleMode(data.mode);
      }
    } catch (error) {
      console.error("Failed to toggle trading mode:", error);
      alert("Error: Could not connect to backend to switch mode.");
    } finally {
      setShowModal(false);
    }
  };

  const cancelToggle = () => {
    setShowModal(false);
  };

  return (
    <>
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          className="flex items-center space-x-2 px-3 py-1.5 rounded-md hover:bg-slate-800/80 transition-colors border border-transparent hover:border-slate-700 focus:outline-none"
        >
          <div className={`w-2 h-2 rounded-full ${tradingMode === 'real' ? 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.8)]' : 'bg-slate-400'}`}></div>
          <span className={`text-sm font-medium ${tradingMode === 'real' ? 'text-purple-300' : 'text-slate-300'}`}>
            {tradingMode === 'real' ? 'Live Account' : 'Paper Account'}
          </span>
          <ChevronDown size={14} className="text-slate-500" />
        </button>

        {isDropdownOpen && (
          <div className="absolute top-full right-0 mt-1 w-44 bg-slate-900 border border-slate-700/50 rounded-md shadow-2xl overflow-hidden z-50 py-1">
            <button 
              className="w-full text-left px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800 transition-colors flex items-center space-x-3"
              onClick={() => handleSelectChange('paper')}
            >
              <div className="w-2 h-2 rounded-full bg-slate-400"></div>
              <span>Paper Account</span>
            </button>
            <button 
              className="w-full text-left px-4 py-2.5 text-sm text-purple-300 hover:bg-slate-800 transition-colors flex items-center space-x-3"
              onClick={() => handleSelectChange('real')}
            >
              <div className="w-2 h-2 rounded-full bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.8)]"></div>
              <span>Live Account</span>
            </button>
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black bg-opacity-75">
          <div className="bg-slate-900 border-2 border-purple-500 rounded-lg p-8 max-w-md text-center shadow-[0_0_25px_rgba(168,85,247,0.4)]">
            <h3 className="text-xl font-black text-red-500 mb-4 uppercase tracking-widest">
              Critical Warning
            </h3>
            <p className="text-slate-300 mb-8 font-medium">
              Switching to LIVE REAL-MONEY trading.<br />
              Are you absolutely sure?
            </p>
            <div className="flex justify-center space-x-6">
              <button
                onClick={cancelToggle}
                className="px-6 py-2 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => executeToggle('real')}
                className="px-6 py-2 rounded bg-red-600 text-white shadow-[0_0_15px_rgba(220,38,38,0.5)] hover:bg-red-500 transition-colors font-bold"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default AccountSwitcher;
