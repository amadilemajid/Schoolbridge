import React, {
  forwardRef,
  useRef,
  useImperativeHandle,
  useState,
  useMemo,
  useEffect,
} from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  type SuggestionCategory,
  DOMAIN_PRESETS,
  getStoredCustomSuggestions,
  saveStoredCustomSuggestion,
} from '../../utils/suggestionDictionaries';
import { Sparkles, Check } from 'lucide-react';

interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  helperTextClassName?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  autoCompleteCategory?: SuggestionCategory | string;
  enableAutoComplete?: boolean;
  suggestions?: string[];
  onAutoComplete?: (completedText: string) => void;
}

// Inferred presets for common school system inputs
const INFERRED_PRESETS: Record<string, string[]> = {
  subject: [
    'Mathematics',
    'English Language',
    'Integrated Science',
    'Social Studies (SST)',
    'Physics',
    'Chemistry',
    'Biology',
    'Geography',
    'History',
    'Commerce',
    'Luganda',
    'Literature in English',
  ],
  district: [
    'Kampala',
    'Wakiso',
    'Mukono',
    'Jinja',
    'Entebbe',
    'Gulu',
    'Mbarara',
    'Arua',
    'Mbale',
    'Masaka',
    'Lira',
    'Kasese',
  ],
  city: [
    'Kampala',
    'Wakiso',
    'Mukono',
    'Jinja',
    'Entebbe',
    'Gulu',
    'Mbarara',
    'Arua',
  ],
  bank: [
    'Stanbic Bank Uganda',
    'Centenary Bank',
    'Equity Bank Uganda',
    'DFCU Bank',
    'Absa Bank Uganda',
    'PostBank Uganda',
    'Bank of Africa Uganda',
  ],
  relationship: [
    'Father',
    'Mother',
    'Guardian',
    'Uncle',
    'Aunt',
    'Brother',
    'Sister',
    'Grandparent',
  ],
  nationality: [
    'Ugandan',
    'South Sudanese',
    'Kenyan',
    'Rwandan',
    'Congolese',
    'Tanzanian',
    'Burundian',
  ],
  religion: [
    'Catholic',
    'Anglican / Protestant',
    'Muslim',
    'Pentecostal / Born Again',
    'Seventh Day Adventist',
    'Orthodox',
  ],
};

function inferPresetKey(identifier: string): string | null {
  const s = identifier.toLowerCase();
  for (const key of Object.keys(INFERRED_PRESETS)) {
    if (s.includes(key)) return key;
  }
  return null;
}

function inferCategory(identifier: string): SuggestionCategory | null {
  const s = identifier.toLowerCase();
  if (s.includes('excuse') || s.includes('leave')) return 'excused_reasons';
  if (s.includes('late')) return 'late_reasons';
  if (s.includes('absent') || s.includes('absence')) return 'absence_reasons';
  if (s.includes('remark') || s.includes('comment') || s.includes('feedback'))
    return 'academic_remarks';
  if (s.includes('reject')) return 'rejection_reasons';
  if (s.includes('unlock')) return 'unlock_reasons';
  if (s.includes('waiver') || s.includes('discount') || s.includes('scholarship'))
    return 'waiver_reasons';
  if (
    s.includes('deactivat') ||
    s.includes('withdraw') ||
    s.includes('transfer')
  )
    return 'deactivation_reasons';
  if (s.includes('note') || s.includes('reason')) return 'excused_reasons';
  return null;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  (
    {
      label,
      error,
      helperText,
      helperTextClassName,
      leftIcon,
      rightIcon,
      className,
      id,
      name,
      type = 'text',
      autoCompleteCategory,
      enableAutoComplete = true,
      suggestions: explicitSuggestions,
      onAutoComplete,
      value,
      defaultValue,
      onChange,
      onKeyDown,
      onBlur,
      placeholder,
      ...props
    },
    ref
  ) => {
    const inputId =
      id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
    const internalInputRef = useRef<HTMLInputElement>(null);
    useImperativeHandle(
      ref,
      () => internalInputRef.current as HTMLInputElement
    );

    const [isDropdownOpen, setIsDropdownOpen] = useState(false);
    const [highlightedIndex, setHighlightedIndex] = useState(-1);
    const [localValue, setLocalValue] = useState<string>(
      value != null ? String(value) : defaultValue != null ? String(defaultValue) : ''
    );

    // Keep internal text track in sync with controlled value
    useEffect(() => {
      if (value !== undefined) {
        setLocalValue(String(value));
      }
    }, [value]);

    const isCompletionEligible =
      enableAutoComplete &&
      type !== 'password' &&
      type !== 'number' &&
      type !== 'date' &&
      type !== 'file';

    const identifier = `${inputId || ''} ${name || ''} ${label || ''} ${placeholder || ''}`.trim();

    // Resolve candidates for autocompletion
    const candidates = useMemo(() => {
      if (!isCompletionEligible) return [];

      if (explicitSuggestions && explicitSuggestions.length > 0) {
        return explicitSuggestions;
      }

      const activeCategory =
        autoCompleteCategory || inferCategory(identifier);

      if (activeCategory) {
        const presets =
          DOMAIN_PRESETS[activeCategory as SuggestionCategory] || [];
        const custom = getStoredCustomSuggestions(activeCategory);
        return Array.from(new Set([...custom, ...presets]));
      }

      const presetKey = inferPresetKey(identifier);
      if (presetKey && INFERRED_PRESETS[presetKey]) {
        return INFERRED_PRESETS[presetKey];
      }

      // Default to input's own learned history
      if (inputId || name) {
        const fieldKey = inputId || name || 'field';
        return getStoredCustomSuggestions(`input_${fieldKey}`);
      }

      return [];
    }, [
      isCompletionEligible,
      explicitSuggestions,
      autoCompleteCategory,
      identifier,
      inputId,
      name,
    ]);

    // Compute top matching ghost completion
    const ghostCompletion = useMemo(() => {
      if (!isCompletionEligible || !localValue || localValue.trim().length < 1) {
        return null;
      }

      const q = localValue.toLowerCase();
      const match = candidates.find((c) =>
        c.toLowerCase().startsWith(q) && c.toLowerCase() !== q
      );

      if (!match) return null;
      // Preserve typed case, append remainder
      return localValue + match.slice(localValue.length);
    }, [isCompletionEligible, localValue, candidates]);

    // Matching suggestions for dropdown
    const matchingSuggestions = useMemo(() => {
      if (!isCompletionEligible || !localValue.trim()) {
        return candidates.slice(0, 6);
      }
      const q = localValue.toLowerCase().trim();
      return candidates
        .filter((c) => c.toLowerCase().includes(q))
        .slice(0, 6);
    }, [isCompletionEligible, localValue, candidates]);

    // Accept completion and dispatch input event
    const handleAcceptCompletion = (completedText: string) => {
      setLocalValue(completedText);
      setIsDropdownOpen(false);
      setHighlightedIndex(-1);

      if (internalInputRef.current) {
        const nativeSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          'value'
        )?.set;
        if (nativeSetter) {
          nativeSetter.call(internalInputRef.current, completedText);
        } else {
          internalInputRef.current.value = completedText;
        }
        const event = new Event('input', { bubbles: true });
        internalInputRef.current.dispatchEvent(event);
      }

      onAutoComplete?.(completedText);

      // Save to history
      const fieldKey =
        autoCompleteCategory || (inputId ? `input_${inputId}` : null);
      if (fieldKey) {
        saveStoredCustomSuggestion(fieldKey, completedText);
      }
    };

    // Keyboard handlers: Tab / RightArrow / DownArrow
    const handleInternalKeyDown = (
      e: React.KeyboardEvent<HTMLInputElement>
    ) => {
      if (
        isCompletionEligible &&
        (e.key === 'Tab' ||
          (e.key === 'ArrowRight' &&
            internalInputRef.current?.selectionStart === localValue.length))
      ) {
        if (ghostCompletion) {
          e.preventDefault();
          handleAcceptCompletion(ghostCompletion);
          return;
        }
        if (
          isDropdownOpen &&
          highlightedIndex >= 0 &&
          matchingSuggestions[highlightedIndex]
        ) {
          e.preventDefault();
          handleAcceptCompletion(matchingSuggestions[highlightedIndex]);
          return;
        }
      } else if (isCompletionEligible && e.key === 'ArrowDown') {
        if (!isDropdownOpen && matchingSuggestions.length > 0) {
          e.preventDefault();
          setIsDropdownOpen(true);
          setHighlightedIndex(0);
        } else if (isDropdownOpen) {
          e.preventDefault();
          setHighlightedIndex((prev) =>
            prev < matchingSuggestions.length - 1 ? prev + 1 : 0
          );
        }
      } else if (isCompletionEligible && e.key === 'ArrowUp') {
        if (isDropdownOpen) {
          e.preventDefault();
          setHighlightedIndex((prev) =>
            prev > 0 ? prev - 1 : matchingSuggestions.length - 1
          );
        }
      } else if (isCompletionEligible && e.key === 'Enter') {
        if (
          isDropdownOpen &&
          highlightedIndex >= 0 &&
          matchingSuggestions[highlightedIndex]
        ) {
          e.preventDefault();
          handleAcceptCompletion(matchingSuggestions[highlightedIndex]);
          return;
        }
      } else if (e.key === 'Escape') {
        setIsDropdownOpen(false);
        setHighlightedIndex(-1);
      }

      onKeyDown?.(e);
    };

    const handleInternalChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      setLocalValue(e.target.value);
      onChange?.(e);
    };

    const handleInternalBlur = (e: React.FocusEvent<HTMLInputElement>) => {
      // Delay closing dropdown so click events register
      setTimeout(() => {
        setIsDropdownOpen(false);
        setHighlightedIndex(-1);
      }, 200);

      const trimmed = e.target.value.trim();
      if (trimmed && isCompletionEligible) {
        const fieldKey =
          autoCompleteCategory || (inputId ? `input_${inputId}` : null);
        if (fieldKey) {
          saveStoredCustomSuggestion(fieldKey, trimmed);
        }
      }

      onBlur?.(e);
    };

    return (
      <div className="w-full flex flex-col gap-1.5 relative">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-slate-300 flex items-center justify-between"
          >
            <span>{label}</span>
            {ghostCompletion && (
              <span className="text-[11px] font-normal text-emerald-400/90 animate-pulse flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-emerald-400" />
                Press Tab ⇥ to complete
              </span>
            )}
          </label>
        )}

        <div className="relative flex items-center">
          {leftIcon && (
            <div className="absolute left-3.5 text-slate-400 pointer-events-none z-10 flex items-center justify-center">
              {leftIcon}
            </div>
          )}

          {/* ── Ghost Auto-completion Overlay ───────────────────────── */}
          {ghostCompletion && !props.disabled && (
            <div
              aria-hidden="true"
              className={twMerge(
                clsx(
                  'absolute inset-0 pointer-events-none flex items-center px-3.5 py-2.5 text-sm select-none overflow-hidden whitespace-nowrap bg-transparent z-0',
                  leftIcon && 'pl-10',
                  rightIcon && 'pr-20',
                  className
                )
              )}
            >
              <span className="opacity-0">{localValue}</span>
              <span className="text-slate-500 italic font-medium">
                {ghostCompletion.slice(localValue.length)}
              </span>
              <span className="ml-2.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-900 text-emerald-400 border border-slate-700/80 shadow-sm shrink-0">
                Tab ⇥
              </span>
            </div>
          )}

          <input
            ref={internalInputRef}
            id={inputId}
            name={name}
            type={type}
            value={value}
            defaultValue={defaultValue}
            placeholder={placeholder}
            aria-invalid={!!error}
            aria-describedby={
              error
                ? `${inputId}-error`
                : helperText
                ? `${inputId}-helper`
                : undefined
            }
            onChange={handleInternalChange}
            onKeyDown={handleInternalKeyDown}
            onBlur={handleInternalBlur}
            className={twMerge(
              clsx(
                'w-full bg-slate-800 border border-slate-700 text-slate-100 placeholder-slate-500 rounded-lg px-3.5 py-2.5 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent min-h-[44px] relative z-0',
                leftIcon && 'pl-10',
                rightIcon && 'pr-10',
                error && 'border-rose-500 focus:ring-rose-500',
                className
              )
            )}
            {...props}
          />

          {rightIcon && (
            <div className="absolute right-3.5 text-slate-400 z-10">
              {rightIcon}
            </div>
          )}
        </div>

        {/* ── Dropdown Suggestions (When ArrowDown pressed) ──────────── */}
        {isDropdownOpen && matchingSuggestions.length > 0 && (
          <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-slate-900/95 backdrop-blur-xl border border-slate-700/90 rounded-xl shadow-2xl overflow-hidden animate-in fade-in-50">
            <div className="p-1.5 border-b border-slate-800 flex items-center justify-between text-[10px] text-slate-400 px-2.5 font-medium">
              <span className="flex items-center gap-1 text-emerald-400 font-semibold">
                <Sparkles className="w-3 h-3" />
                Auto-completions
              </span>
              <span>Press Tab or Enter</span>
            </div>

            <ul className="max-h-48 overflow-y-auto divide-y divide-slate-800/40 p-1">
              {matchingSuggestions.map((item, idx) => {
                const isHighlighted = idx === highlightedIndex;
                const isExact =
                  item.toLowerCase() === localValue.toLowerCase();

                return (
                  <li
                    key={`${item}-${idx}`}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      handleAcceptCompletion(item);
                    }}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    className={clsx(
                      'px-3 py-2 text-xs rounded-lg cursor-pointer flex items-center justify-between gap-2 transition-colors select-none',
                      isHighlighted
                        ? 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/30'
                        : 'text-slate-300 hover:bg-slate-800/70',
                      isExact && 'font-semibold text-emerald-400'
                    )}
                  >
                    <span className="truncate">{item}</span>
                    {isExact && (
                      <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {error ? (
          <p id={`${inputId}-error`} className="text-xs text-rose-400 mt-0.5">
            {error}
          </p>
        ) : helperText ? (
          <p
            id={`${inputId}-helper`}
            className={twMerge(
              'text-xs text-slate-400 mt-0.5',
              helperTextClassName
            )}
          >
            {helperText}
          </p>
        ) : null}
      </div>
    );
  }
);

TextInput.displayName = 'TextInput';

export default TextInput;
