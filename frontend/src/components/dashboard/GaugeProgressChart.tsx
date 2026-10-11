import React from 'react';

interface GaugeProgressChartProps {
  percentage: number;
  label?: string;
  sublabel?: string;
}

export const GaugeProgressChart: React.FC<GaugeProgressChartProps> = ({
  percentage,
  label = 'Term Collection Rate',
  sublabel = 'Target: 100%',
}) => {
  const cappedPercentage = Math.min(Math.max(percentage, 0), 100);
  const strokeDashoffset = 283 - (283 * cappedPercentage) / 100;

  return (
    <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 flex flex-col items-center justify-center text-center shadow-xl">
      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">{label}</h4>

      <div className="relative w-40 h-40 flex items-center justify-center">
        {/* SVG Circular Progress Gauge */}
        <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
          <circle
            cx="50"
            cy="50"
            r="45"
            className="text-slate-700 stroke-current"
            strokeWidth="8"
            fill="transparent"
          />
          <circle
            cx="50"
            cy="50"
            r="45"
            className="text-emerald-500 stroke-current transition-all duration-1000 ease-out"
            strokeWidth="8"
            strokeDasharray="283"
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
          />
        </svg>

        <div className="absolute flex flex-col items-center">
          <span className="text-3xl font-extrabold text-white tracking-tight">
            {cappedPercentage.toFixed(1)}%
          </span>
          <span className="text-[10px] text-emerald-400 font-semibold uppercase mt-0.5">{sublabel}</span>
        </div>
      </div>
    </div>
  );
};
