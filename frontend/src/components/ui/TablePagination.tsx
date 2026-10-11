import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface TablePaginationProps {
  currentPage: number;
  totalCount: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
}

export const TablePagination: React.FC<TablePaginationProps> = ({
  currentPage,
  totalCount,
  pageSize,
  onPageChange,
  onPageSizeChange,
}) => {
  const totalPages = Math.ceil(totalCount / pageSize);
  const startItem = ((currentPage - 1) * pageSize) + 1;
  const endItem = Math.min(currentPage * pageSize, totalCount);

  // Build a compact page list: always show first, last, current ±1, with ellipsis gaps
  const getPageNumbers = (): (number | 'ellipsis')[] => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages: (number | 'ellipsis')[] = [];
    const range = new Set([1, 2, currentPage - 1, currentPage, currentPage + 1, totalPages - 1, totalPages]);
    let prev = 0;
    Array.from(range)
      .filter((p) => p >= 1 && p <= totalPages)
      .sort((a, b) => a - b)
      .forEach((p) => {
        if (prev && p - prev > 1) pages.push('ellipsis');
        pages.push(p);
        prev = p;
      });
    return pages;
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 px-1">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span>Rows per page:</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange?.(Number(e.target.value))}
          className="bg-slate-800 border border-slate-700 text-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {[10, 25, 50, 100].map((size) => (
            <option key={size} value={size}>{size}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-400">
          {totalCount === 0 ? '0' : `${startItem}–${endItem}`} of {totalCount.toLocaleString()} records
        </span>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage <= 1}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors border border-slate-700/60"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            <span>Prev</span>
          </button>

          {getPageNumbers().map((p, idx) =>
            p === 'ellipsis' ? (
              <span key={`ellipsis-${idx}`} className="text-xs text-slate-500 px-1">…</span>
            ) : (
              <button
                key={p}
                onClick={() => onPageChange(p)}
                className={`min-w-[28px] h-7 px-2 rounded-lg text-xs font-semibold transition-all border ${
                  currentPage === p
                    ? 'bg-emerald-600 border-emerald-500 text-white shadow-sm'
                    : 'bg-slate-800 border-slate-700/60 text-slate-300 hover:border-slate-500 hover:text-white'
                }`}
              >
                {p}
              </button>
            )
          )}

          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage >= totalPages}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors border border-slate-700/60"
            aria-label="Next page"
          >
            <span>Next</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
