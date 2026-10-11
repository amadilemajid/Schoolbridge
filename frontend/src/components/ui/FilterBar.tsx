import React from 'react';
import { Search, X } from 'lucide-react';

export interface ActiveFilter {
  key: string;
  label: string;
  value: string;
}

interface FilterBarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  activeFilters?: ActiveFilter[];
  onRemoveFilter?: (key: string) => void;
  onResetAll?: () => void;
  children?: React.ReactNode; // Slot for dropdown selects
}

export const FilterBar: React.FC<FilterBarProps> = ({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search...',
  activeFilters = [],
  onRemoveFilter,
  onResetAll,
  children,
}) => {
  return (
    <div className="space-y-3">
      {/* Main Filter Row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search Input */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            type="search"
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 text-slate-100 placeholder-slate-500 rounded-xl pl-10 pr-4 py-2.5 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
          />
        </div>

        {/* Filter Slot (Dropdowns injected as children) */}
        {children}

        {/* Reset All Filters */}
        {(activeFilters.length > 0 || searchValue) && (
          <button
            onClick={onResetAll}
            className="text-xs text-slate-400 hover:text-rose-400 transition-colors flex items-center gap-1.5 px-3 py-2.5 rounded-xl hover:bg-slate-800"
          >
            <X className="w-3.5 h-3.5" />
            Reset filters
          </button>
        )}
      </div>

      {/* Active Filter Pills */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {activeFilters.map((filter) => (
            <span
              key={filter.key}
              className="inline-flex items-center gap-1.5 text-xs bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 rounded-full px-3 py-1 font-medium"
            >
              {filter.label}: <span className="font-bold">{filter.value}</span>
              <button
                onClick={() => onRemoveFilter?.(filter.key)}
                className="text-emerald-400 hover:text-white transition-colors"
                aria-label={`Remove ${filter.label} filter`}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
