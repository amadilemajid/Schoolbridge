import React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { clsx } from 'clsx';

interface KpiCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: React.ReactNode;
  subtitle?: string;
  isLoading?: boolean;
  onClick?: () => void;
  clickableHint?: string;
  isActive?: boolean;
  className?: string;
}

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  value,
  change,
  changeType = 'positive',
  icon,
  subtitle,
  isLoading = false,
  onClick,
  clickableHint,
  isActive = false,
  className,
}) => {
  if (isLoading) {
    return (
      <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 animate-pulse">
        <div className="flex items-center justify-between mb-3">
          <div className="h-4 bg-slate-700 rounded w-24" />
          <div className="w-10 h-10 bg-slate-700 rounded-xl" />
        </div>
        <div className="h-8 bg-slate-700 rounded w-36 mb-2" />
        <div className="h-3 bg-slate-700 rounded w-20" />
      </div>
    );
  }

  const isInteractive = Boolean(onClick);

  return (
    <div
      onClick={onClick}
      role={isInteractive ? 'button' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
      onKeyDown={
        isInteractive
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={clsx(
        'bg-slate-800/80 backdrop-blur-md rounded-2xl p-5 transition-all select-none',
        isActive
          ? 'border-2 border-emerald-500 ring-2 ring-emerald-500/30 bg-slate-800/95 shadow-xl shadow-emerald-950/40 -translate-y-0.5'
          : 'border border-slate-700/60 shadow-xl',
        isInteractive && !isActive && 'cursor-pointer hover:border-emerald-500/50 hover:bg-slate-800/95 hover:shadow-emerald-950/20 active:scale-[0.99] group',
        isInteractive && isActive && 'cursor-pointer active:scale-[0.99] group',
        !isInteractive && 'hover:border-slate-600',
        className
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={clsx(
            "text-xs font-semibold uppercase tracking-wider transition-colors",
            isActive ? "text-emerald-400 font-bold" : "text-slate-400 group-hover:text-slate-300"
          )}>
            {title}
          </span>
          {isActive && (
            <span className="text-[9px] font-bold text-emerald-300 bg-emerald-500/20 border border-emerald-500/40 px-1.5 py-0.2 rounded-full uppercase tracking-wider animate-pulse">
              Selected
            </span>
          )}
        </div>
        <div
          className={clsx(
            'w-10 h-10 rounded-xl bg-slate-900 border flex items-center justify-center transition-all',
            isActive ? 'border-emerald-500/60 text-emerald-300 scale-105 shadow-md shadow-emerald-950/50' : 'border-slate-700 text-emerald-400',
            isInteractive && !isActive && 'group-hover:border-emerald-500/40 group-hover:scale-105 group-hover:shadow-md'
          )}
        >
          {icon}
        </div>
      </div>

      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-2xl font-bold text-white tracking-tight group-hover:text-emerald-300 transition-colors">
          {value}
        </h3>

        {change && (
          <div
            className={clsx(
              'inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full',
              changeType === 'positive' && 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
              changeType === 'negative' && 'bg-rose-500/10 text-rose-400 border border-rose-500/20',
              changeType === 'neutral' && 'bg-slate-700 text-slate-300'
            )}
          >
            {changeType === 'positive' && <ArrowUpRight className="w-3 h-3 mr-0.5" />}
            {changeType === 'negative' && <ArrowDownRight className="w-3 h-3 mr-0.5" />}
            <span>{change}</span>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-1">
        {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
        {isInteractive && (
          <span className={clsx(
            "text-[11px] font-medium transition-colors flex items-center gap-0.5 ml-auto",
            isActive ? "text-emerald-400 font-semibold" : "text-slate-500 group-hover:text-emerald-400"
          )}>
            {clickableHint || 'View details'} &rarr;
          </span>
        )}
      </div>
    </div>
  );
};
