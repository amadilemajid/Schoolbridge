import React, { useState, useRef, useEffect } from 'react';
import { Search, ChevronDown, ChevronRight, Check } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
}

interface SearchableSelectProps {
  label: string;
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  label,
  options,
  value,
  onChange,
  placeholder = 'Select...',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  const filteredOptions = options.filter((opt) =>
    opt.label.toLowerCase().includes(searchQuery.toLowerCase())
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="flex flex-col gap-1.5 flex-1 relative" ref={containerRef}>
      <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
        {label}
      </label>

      {/* Select Trigger */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-slate-800/90 border border-slate-700 hover:border-blue-500/50 text-slate-100 rounded-xl px-4 py-3 text-sm flex items-center justify-between transition-all duration-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
      >
        <span className={selectedOption ? 'text-slate-100 font-medium' : 'text-slate-400'}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <div className="flex items-center gap-1 text-slate-400">
          {isOpen ? <ChevronDown className="w-4 h-4 text-blue-400" /> : <ChevronRight className="w-4 h-4" />}
        </div>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-2 z-50 bg-slate-800 border border-slate-700/80 rounded-xl shadow-2xl overflow-hidden p-2 backdrop-blur-xl animate-in fade-in-50 zoom-in-95 duration-150">
          {/* Search Input inside Dropdown */}
          <div className="relative mb-2">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search..."
              autoFocus
              className="w-full bg-slate-900/90 border border-slate-700/60 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Options List */}
          <div className="max-h-56 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-3 text-xs text-slate-500 text-center">
                No matching options found
              </div>
            ) : (
              filteredOptions.map((opt) => {
                const isSelected = opt.value === value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => {
                      onChange(opt.value);
                      setIsOpen(false);
                      setSearchQuery('');
                    }}
                    className={`w-full text-left px-3 py-2 rounded-lg text-xs font-medium flex items-center justify-between transition-colors ${
                      isSelected
                        ? 'bg-blue-600 text-white font-semibold'
                        : 'text-slate-200 hover:bg-blue-500/10 hover:text-blue-400'
                    }`}
                  >
                    <span>{opt.label}</span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
