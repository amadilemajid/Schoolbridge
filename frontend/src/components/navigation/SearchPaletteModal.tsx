import React, { useState, useEffect } from 'react';
import { Search, CreditCard, Users, CalendarCheck, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface SearchPaletteModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SearchPaletteModal: React.FC<SearchPaletteModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) {
          onClose();
        } else {
          // Open search modal via global event
          window.dispatchEvent(new CustomEvent('open-search-modal'));
        }
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const quickShortcuts = [
    {
      title: 'Record Cash Payment',
      subtitle: 'Open bursar rapid payment workflow',
      icon: CreditCard,
      action: () => {
        navigate('/finance');
        onClose();
      },
    },
    {
      title: 'Student Directory',
      subtitle: 'Search student ledgers & parents',
      icon: Users,
      action: () => {
        navigate('/students');
        onClose();
      },
    },
    {
      title: 'Mark Morning Attendance',
      subtitle: 'Launch 7 AM-12 PM daily register',
      icon: CalendarCheck,
      action: () => {
        navigate('/attendance');
        onClose();
      },
    },
    {
      title: 'Class Timetables & Schedules',
      subtitle: 'View weekly subject timetable by class stream',
      icon: CalendarCheck,
      action: () => {
        navigate('/academics/timetable');
        onClose();
      },
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 sm:pt-24 p-4">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />

      {/* Modal Dialog */}
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden z-10">
        {/* Search Input Bar */}
        <div className="p-4 border-b border-slate-800 flex items-center gap-3">
          <Search className="w-5 h-5 text-emerald-400 shrink-0" />
          <input
            type="text"
            placeholder="Type student name, ID, guardian phone (+256), or shortcut..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            className="w-full bg-transparent text-slate-100 placeholder-slate-500 text-sm focus:outline-none"
          />
          <kbd className="hidden sm:inline-block text-[10px] font-mono px-2 py-0.5 bg-slate-800 border border-slate-700 rounded text-slate-400">
            ESC
          </kbd>
        </div>

        {/* Quick Shortcuts */}
        <div className="p-4 space-y-2 max-h-80 overflow-y-auto">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 px-2">
            Quick Action Shortcuts
          </span>

          <div className="space-y-1 mt-1">
            {quickShortcuts.map((item, idx) => {
              const Icon = item.icon;
              return (
                <button
                  key={idx}
                  onClick={item.action}
                  className="w-full flex items-center justify-between p-3 rounded-xl hover:bg-slate-800 transition-colors group text-left"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-emerald-400 group-hover:border-emerald-500 transition-colors">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <h5 className="text-xs font-semibold text-slate-200 group-hover:text-white">
                        {item.title}
                      </h5>
                      <p className="text-[10px] text-slate-400">{item.subtitle}</p>
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 transition-colors" />
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
