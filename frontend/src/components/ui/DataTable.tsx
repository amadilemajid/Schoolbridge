import React from 'react';

export interface Column<T> {
  header: string;
  accessorKey?: keyof T;
  cell?: (row: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  isLoading?: boolean;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
}

export function DataTable<T extends { id: string | number }>({
  columns,
  data,
  isLoading = false,
  onRowClick,
  emptyMessage = 'No records found matching your filters.',
}: DataTableProps<T>) {
  if (isLoading) {
    return (
      <div className="w-full bg-slate-800/80 border border-slate-700/60 rounded-2xl p-8 text-center animate-pulse">
        <div className="space-y-4">
          <div className="h-6 bg-slate-700 rounded w-full" />
          <div className="h-6 bg-slate-700 rounded w-full" />
          <div className="h-6 bg-slate-700 rounded w-full" />
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="w-full bg-slate-800/80 border border-slate-700/60 rounded-2xl p-12 text-center">
        <p className="text-sm font-medium text-slate-400">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="w-full bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl overflow-hidden shadow-xl">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-900/50 text-slate-400 uppercase tracking-wider font-semibold">
              {columns.map((col, idx) => (
                <th key={idx} className={`py-3.5 px-4 ${col.className || ''}`}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {data.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick && onRowClick(row)}
                className={`transition-colors ${
                  onRowClick ? 'cursor-pointer hover:bg-slate-700/40' : 'hover:bg-slate-700/20'
                }`}
              >
                {columns.map((col, idx) => (
                  <td key={idx} className={`py-3.5 px-4 text-slate-200 ${col.className || ''}`}>
                    {col.cell
                      ? col.cell(row)
                      : col.accessorKey
                      ? (row[col.accessorKey] as React.ReactNode)
                      : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
