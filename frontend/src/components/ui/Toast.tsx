import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react';
import { clsx } from 'clsx';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  onClose: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({ id, type, title, message, onClose }) => {
  const icons = {
    success: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />,
    error: <XCircle className="w-5 h-5 text-rose-400 shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />,
    info: <Info className="w-5 h-5 text-indigo-400 shrink-0" />,
  };

  const borderStyles = {
    success: 'border-emerald-500/30 bg-slate-850',
    error: 'border-rose-500/30 bg-slate-850',
    warning: 'border-amber-500/30 bg-slate-850',
    info: 'border-indigo-500/30 bg-slate-850',
  };

  return (
    <div
      role="alert"
      className={clsx(
        'flex items-start gap-3 p-4 rounded-xl border bg-slate-800 shadow-2xl transition-all duration-300 max-w-sm w-full',
        borderStyles[type]
      )}
    >
      {icons[type]}
      <div className="flex-1 text-sm">
        <h4 className="font-semibold text-slate-100">{title}</h4>
        {message && <p className="text-slate-400 text-xs mt-0.5">{message}</p>}
      </div>
      <button
        onClick={() => onClose(id)}
        className="text-slate-400 hover:text-slate-200 transition-colors p-1 rounded-md"
        aria-label="Close notification"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
