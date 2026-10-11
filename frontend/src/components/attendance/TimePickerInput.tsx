import React, { useState, useRef, useEffect } from 'react';
import { Clock } from 'lucide-react';

interface TimePickerInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
}

const HOURS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];
const MINUTES = ['00', '05', '10', '15', '20', '25', '30', '35', '40', '45', '50', '55'];
const PERIODS = ['AM', 'PM'];

export const TimePickerInput: React.FC<TimePickerInputProps> = ({ label, value, onChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Parse current value e.g. "12:05 PM"
  const parseTime = (val: string) => {
    const parts = val.split(' ');
    const period = parts[1] || 'AM';
    const timeParts = (parts[0] || '12:00').split(':');
    return {
      hour: timeParts[0] || '12',
      minute: timeParts[1] || '00',
      period,
    };
  };

  const current = parseTime(value);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const updateHour = (h: string) => {
    onChange(`${h}:${current.minute} ${current.period}`);
  };

  const updateMinute = (m: string) => {
    onChange(`${current.hour}:${m} ${current.period}`);
  };

  const updatePeriod = (p: string) => {
    onChange(`${current.hour}:${current.minute} ${p}`);
  };

  return (
    <div className="flex flex-col gap-1 relative" ref={containerRef}>
      <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{label}</label>
      
      {/* Time Display Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="bg-slate-800/90 border border-slate-700 hover:border-blue-500/50 text-slate-100 rounded-xl px-3 py-2.5 text-xs font-semibold flex items-center justify-between gap-2 min-w-[130px] transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
      >
        <div className="flex items-center gap-1.5 text-slate-300">
          <Clock className="w-3.5 h-3.5 text-blue-400" />
          <span>{value}</span>
        </div>
        <Clock className="w-3.5 h-3.5 text-slate-500" />
      </button>

      {/* Time Picker Popover (3 Columns: Hour, Minute, AM/PM) */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-2 z-50 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl p-2 backdrop-blur-xl flex gap-1 w-64 border-t-2 border-t-blue-500 animate-in fade-in-50 zoom-in-95 duration-150">
          {/* Hours Column */}
          <div className="flex-1 space-y-1 max-h-48 overflow-y-auto custom-scrollbar pr-0.5">
            <div className="text-[10px] font-bold text-slate-400 text-center pb-1 border-b border-slate-700">HR</div>
            {HOURS.map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => updateHour(h)}
                className={`w-full py-1 rounded text-xs font-semibold text-center transition-colors ${
                  current.hour === h
                    ? 'bg-blue-600 text-white font-bold'
                    : 'text-slate-300 hover:bg-slate-700/60'
                }`}
              >
                {h}
              </button>
            ))}
          </div>

          {/* Minutes Column */}
          <div className="flex-1 space-y-1 max-h-48 overflow-y-auto custom-scrollbar px-0.5 border-x border-slate-700/50">
            <div className="text-[10px] font-bold text-slate-400 text-center pb-1 border-b border-slate-700">MIN</div>
            {MINUTES.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => updateMinute(m)}
                className={`w-full py-1 rounded text-xs font-semibold text-center transition-colors ${
                  current.minute === m
                    ? 'bg-blue-600 text-white font-bold'
                    : 'text-slate-300 hover:bg-slate-700/60'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {/* AM / PM Column */}
          <div className="w-14 space-y-1 pl-0.5">
            <div className="text-[10px] font-bold text-slate-400 text-center pb-1 border-b border-slate-700">PER</div>
            {PERIODS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => updatePeriod(p)}
                className={`w-full py-1.5 rounded text-xs font-bold text-center transition-colors ${
                  current.period === p
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:bg-slate-700/60'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
