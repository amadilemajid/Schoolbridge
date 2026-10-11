import React from 'react';
import { AlertTriangle, Info, CheckCircle2, X } from 'lucide-react';
import { clsx } from 'clsx';

interface AlertBannerProps {
  type?: 'warning' | 'info' | 'success' | 'error';
  title: string;
  message?: string;
  onDismiss?: () => void;
  actionButton?: React.ReactNode;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({
  type = 'warning',
  title,
  message,
  onDismiss,
  actionButton,
}) => {
  const icons = {
    warning: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />,
    info: <Info className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />,
    success: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />,
    error: <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />,
  };

  const bgStyles = {
    warning: 'bg-amber-500/10 border-amber-500/30 text-amber-200',
    info: 'bg-indigo-500/10 border-indigo-500/30 text-indigo-200',
    success: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200',
    error: 'bg-rose-500/10 border-rose-500/30 text-rose-200',
  };

  return (
    <div className={clsx('p-4 rounded-xl border flex items-start justify-between gap-4', bgStyles[type])}>
      <div className="flex items-start gap-3">
        {icons[type]}
        <div>
          <h4 className="text-sm font-semibold text-white">{title}</h4>
          {message && <p className="text-xs text-slate-300 mt-0.5">{message}</p>}
          {actionButton && <div className="mt-3">{actionButton}</div>}
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-slate-400 hover:text-white p-1 rounded-md"
          aria-label="Dismiss banner"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};
