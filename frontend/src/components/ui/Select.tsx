import React, { forwardRef } from 'react';
import { clsx } from 'clsx';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  error?: string;
  helperText?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(({
  label,
  options,
  error,
  helperText,
  className,
  id,
  ...props
}, ref) => {
  const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="w-full flex flex-col gap-1.5">
      {label && (
        <label htmlFor={selectId} className="text-sm font-medium text-slate-300">
          {label}
        </label>
      )}

      <select
        ref={ref}
        id={selectId}
        aria-invalid={!!error}
        className={clsx(
          'w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-3.5 py-2.5 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent min-h-[44px]',
          error && 'border-rose-500 focus:ring-rose-500',
          className
        )}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-slate-800 text-slate-100">
            {opt.label}
          </option>
        ))}
      </select>

      {error ? (
        <p className="text-xs text-rose-400 mt-0.5">{error}</p>
      ) : helperText ? (
        <p className="text-xs text-slate-400 mt-0.5">{helperText}</p>
      ) : null}
    </div>
  );
});

Select.displayName = 'Select';
