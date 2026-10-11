import React from 'react';

interface TrendPoint {
  date: string;
  amount: number;
}

interface AreaTrendChartProps {
  data: TrendPoint[];
  title?: string;
  subtitle?: string;
}

export const AreaTrendChart: React.FC<AreaTrendChartProps> = ({
  data,
  title = '14-Day Collection Trend',
  subtitle,
}) => {
  const total14Day = data.reduce((sum, d) => sum + (d.amount || 0), 0);
  const maxAmount = Math.max(...data.map(d => d.amount || 0), 1);

  return (
    <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl flex flex-col justify-between">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-6">
        <div>
          <h4 className="text-xs font-bold text-white uppercase tracking-wider">{title}</h4>
          {subtitle ? (
            <p className="text-[11px] text-slate-400 mt-0.5">{subtitle}</p>
          ) : (
            <p className="text-[11px] text-slate-400 mt-0.5">Daily cash & mobile money intake</p>
          )}
        </div>
        <span className="text-xs text-emerald-400 font-semibold bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 whitespace-nowrap self-start sm:self-auto">
          UGX {total14Day.toLocaleString()} (14 Days)
        </span>
      </div>

      <div className="h-44 flex items-end justify-between gap-1.5 sm:gap-2 pt-4">
        {data.map((pt, idx) => {
          const hasAmount = pt.amount > 0;
          const heightPercent = hasAmount ? Math.max((pt.amount / maxAmount) * 100, 8) : 0;
          const isLast = idx === data.length - 1;

          return (
            <div
              key={idx}
              className="flex-1 max-w-[48px] flex flex-col items-center gap-2 group relative"
            >
              {/* Tooltip on hover */}
              <div className="absolute -top-12 opacity-0 group-hover:opacity-100 transition-all duration-200 bg-slate-900/95 border border-slate-700 text-[10px] px-2.5 py-1.5 rounded-lg shadow-2xl whitespace-nowrap pointer-events-none z-30 flex flex-col items-center">
                <span className="text-[9px] text-slate-400 font-mono">{pt.date}</span>
                <span className={hasAmount ? 'font-bold text-emerald-400' : 'text-slate-400'}>
                  UGX {pt.amount.toLocaleString()}
                </span>
              </div>

              {/* Bar Column Container */}
              <div className="w-full bg-slate-700/30 rounded-t-lg h-36 flex items-end overflow-hidden">
                {hasAmount ? (
                  <div
                    style={{ height: `${heightPercent}%` }}
                    className="w-full bg-gradient-to-t from-emerald-600 to-teal-400 rounded-t-lg transition-all duration-500 group-hover:brightness-125 shadow-lg shadow-emerald-950/40"
                  />
                ) : (
                  <div className="w-full h-1 bg-slate-700/50 rounded-full transition-colors group-hover:bg-slate-600" />
                )}
              </div>

              {/* Date Label */}
              <span
                className={`text-[9px] sm:text-[10px] truncate w-full text-center ${
                  isLast
                    ? 'text-emerald-400 font-semibold'
                    : 'text-slate-400 group-hover:text-slate-300'
                }`}
              >
                {isLast ? 'Today' : pt.date.split(' ')[0]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
