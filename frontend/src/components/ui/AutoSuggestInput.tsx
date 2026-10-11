import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  type SuggestionCategory,
  fetchCategorySuggestions,
  saveStoredCustomSuggestion,
  DOMAIN_PRESETS,
  getStoredCustomSuggestions,
} from '../../utils/suggestionDictionaries';
import { Sparkles, ChevronDown, Clock, Check, X, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export interface AutoSuggestInputProps {
  value: string;
  onChange: (value: string) => void;
  onSelectSuggestion?: (suggestion: string) => void;
  category?: SuggestionCategory | string;
  suggestions?: string[];
  placeholder?: string;
  label?: string;
  error?: string;
  helperText?: string;
  disabled?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  className?: string;
  inputClassName?: string;
  showChips?: boolean;
  enableHistory?: boolean;
  minChars?: number;
  maxSuggestions?: number;
  id?: string;
  autoFocus?: boolean;
}

export const AutoSuggestInput: React.FC<AutoSuggestInputProps> = ({
  value,
  onChange,
  onSelectSuggestion,
  category = 'general',
  suggestions: explicitSuggestions,
  placeholder = 'Type or select reason...',
  label,
  error,
  helperText,
  disabled = false,
  leftIcon,
  rightIcon,
  className,
  inputClassName,
  showChips = false,
  enableHistory = true,
  minChars = 0,
  maxSuggestions = 8,
  id,
  autoFocus = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const [fetchedSuggestions, setFetchedSuggestions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch or resolve suggestions
  useEffect(() => {
    let isMounted = true;

    if (explicitSuggestions) {
      setFetchedSuggestions(explicitSuggestions);
      return;
    }

    if (!category) return;

    // Fast initial synchronous populate from local presets + history
    const localHistory = getStoredCustomSuggestions(category);
    const presets = DOMAIN_PRESETS[category as SuggestionCategory] || DOMAIN_PRESETS.general;
    const initialCombined = Array.from(new Set([...localHistory, ...presets]));
    setFetchedSuggestions(initialCombined);

    // Then background fetch from API to get live school-specific records
    setIsLoading(true);
    fetchCategorySuggestions(category, value)
      .then((items) => {
        if (isMounted && items.length > 0) {
          setFetchedSuggestions(items);
        }
      })
      .catch(() => {
        // preserve initial presets on error
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [category, explicitSuggestions]);

  // Filter suggestions based on current value
  const filteredSuggestions = useMemo(() => {
    const rawList = explicitSuggestions || fetchedSuggestions;
    if (!value.trim()) {
      return rawList.slice(0, maxSuggestions);
    }

    const q = value.toLowerCase().trim();
    const startsWith: string[] = [];
    const contains: string[] = [];

    rawList.forEach((item) => {
      const lower = item.toLowerCase();
      if (lower.startsWith(q)) {
        startsWith.push(item);
      } else if (lower.includes(q)) {
        contains.push(item);
      }
    });

    return [...startsWith, ...contains].slice(0, maxSuggestions);
  }, [explicitSuggestions, fetchedSuggestions, value, maxSuggestions]);

  // Handle clicking outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Handle selecting a suggestion
  const handleSelect = (selectedText: string) => {
    onChange(selectedText);
    onSelectSuggestion?.(selectedText);
    if (enableHistory && category) {
      saveStoredCustomSuggestion(category, selectedText);
    }
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  // Top ghost completion match (starts with value case-insensitively)
  const ghostCompletion = useMemo(() => {
    if (!value || value.trim().length < 1) return null;
    const q = value.toLowerCase();
    const candidate = filteredSuggestions.find((s) => s.toLowerCase().startsWith(q));
    if (!candidate || candidate.toLowerCase() === q) return null;
    // Preserves the user's typed case, appends the rest from candidate
    return value + candidate.slice(value.length);
  }, [value, filteredSuggestions]);

  // Handle Keyboard Navigation & Tab Auto-completion
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Tab' || (e.key === 'ArrowRight' && inputRef.current?.selectionStart === value.length)) {
      if (ghostCompletion) {
        e.preventDefault();
        handleSelect(ghostCompletion);
        return;
      }
      if (isOpen && highlightedIndex >= 0 && filteredSuggestions[highlightedIndex]) {
        e.preventDefault();
        handleSelect(filteredSuggestions[highlightedIndex]);
        return;
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setHighlightedIndex(0);
      } else {
        setHighlightedIndex((prev) =>
          prev < filteredSuggestions.length - 1 ? prev + 1 : 0
        );
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setHighlightedIndex(filteredSuggestions.length - 1);
      } else {
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : filteredSuggestions.length - 1
        );
      }
    } else if (e.key === 'Enter') {
      if (isOpen && highlightedIndex >= 0 && filteredSuggestions[highlightedIndex]) {
        e.preventDefault();
        handleSelect(filteredSuggestions[highlightedIndex]);
      } else if (ghostCompletion) {
        e.preventDefault();
        handleSelect(ghostCompletion);
      } else if (value.trim() && enableHistory && category) {
        saveStoredCustomSuggestion(category, value.trim());
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
      setHighlightedIndex(-1);
    }
  };

  // Highlight matching query text in suggestion item
  const renderHighlightedText = (text: string, query: string) => {
    if (!query.trim()) return <span>{text}</span>;

    const q = query.trim().toLowerCase();
    const index = text.toLowerCase().indexOf(q);
    if (index === -1) return <span>{text}</span>;

    const before = text.substring(0, index);
    const match = text.substring(index, index + q.length);
    const after = text.substring(index + q.length);

    return (
      <span>
        {before}
        <span className="font-extrabold text-emerald-400 bg-emerald-500/20 px-0.5 rounded">
          {match}
        </span>
        {after}
      </span>
    );
  };

  return (
    <div ref={containerRef} className={twMerge('relative w-full', className)}>
      {label && (
        <label
          htmlFor={id}
          className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5"
        >
          {label}
        </label>
      )}

      <div className="relative flex items-center">
        {leftIcon && (
          <div className="absolute left-3 text-slate-400 pointer-events-none flex items-center justify-center z-10">
            {leftIcon}
          </div>
        )}

        {/* Ghost Autocomplete Overlay */}
        {ghostCompletion && !disabled && (
          <div
            aria-hidden="true"
            className={twMerge(clsx(
              'absolute inset-0 pointer-events-none flex items-center px-3 py-2 text-xs font-normal select-none overflow-hidden whitespace-nowrap bg-transparent',
              leftIcon && 'pl-9',
              (rightIcon || value) && 'pr-20',
              inputClassName
            ))}
          >
            <span className="opacity-0">{value}</span>
            <span className="text-slate-500 italic font-medium">{ghostCompletion.slice(value.length)}</span>
            <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-emerald-400/90 border border-slate-700/80 shadow-sm shrink-0">
              Tab ⇥
            </span>
          </div>
        )}

        <input
          ref={inputRef}
          id={id}
          type="text"
          value={value}
          disabled={disabled}
          autoFocus={autoFocus}
          placeholder={placeholder}
          onFocus={() => {
            if (value.length >= minChars) {
              setIsOpen(true);
            }
          }}
          onChange={(e) => {
            const next = e.target.value;
            onChange(next);
            if (!isOpen && next.length >= minChars) {
              setIsOpen(true);
            }
            setHighlightedIndex(-1);
          }}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (value.trim() && enableHistory && category) {
              saveStoredCustomSuggestion(category, value.trim());
            }
          }}
          className={twMerge(clsx(
            'w-full bg-slate-900/90 border border-slate-700 text-slate-100 placeholder-slate-500 rounded-lg px-3 py-2 text-xs transition-all focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500/80',
            leftIcon && 'pl-9',
            (rightIcon || value) && 'pr-14',
            error && 'border-rose-500 focus:ring-rose-500',
            disabled && 'opacity-50 cursor-not-allowed',
            inputClassName
          ))}
        />

        {/* Action icons right: clear button & dropdown toggle */}
        <div className="absolute right-2.5 flex items-center gap-1 text-slate-400">
          {value && !disabled && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange('');
                inputRef.current?.focus();
              }}
              className="p-1 hover:text-white rounded transition-colors"
              title="Clear"
            >
              <X className="w-3 h-3" />
            </button>
          )}

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen((prev) => !prev);
              inputRef.current?.focus();
            }}
            className="p-1 hover:text-white rounded transition-colors"
            title="Toggle suggestions"
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
            ) : (
              <ChevronDown
                className={clsx(
                  'w-3.5 h-3.5 transition-transform duration-200',
                  isOpen && 'rotate-180 text-emerald-400'
                )}
              />
            )}
          </button>
        </div>
      </div>

      {/* ── Floating Auto-Suggestion Dropdown ────────────────────────── */}
      {isOpen && filteredSuggestions.length > 0 && !disabled && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-slate-900/95 backdrop-blur-xl border border-slate-700/90 rounded-xl shadow-2xl overflow-hidden animate-in fade-in-50 slide-in-from-top-1">
          <div className="p-1.5 border-b border-slate-800 flex items-center justify-between text-[10px] text-slate-400 font-medium px-2.5">
            <span className="flex items-center gap-1 text-emerald-400 font-semibold">
              <Sparkles className="w-3 h-3" />
              Suggested Reasons
            </span>
            <span>Use ↑↓ arrows to choose</span>
          </div>

          <ul className="max-h-56 overflow-y-auto divide-y divide-slate-800/40 p-1">
            {filteredSuggestions.map((item, idx) => {
              const isSelected = value.trim().toLowerCase() === item.toLowerCase();
              const isHighlighted = idx === highlightedIndex;

              return (
                <li
                  key={`${item}-${idx}`}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  onClick={() => handleSelect(item)}
                  className={clsx(
                    'px-3 py-2 text-xs rounded-lg cursor-pointer flex items-center justify-between gap-2 transition-colors select-none',
                    isHighlighted
                      ? 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/30'
                      : 'text-slate-300 hover:bg-slate-800/70',
                    isSelected && 'font-semibold text-emerald-400'
                  )}
                >
                  <div className="flex items-center gap-2 truncate">
                    <Clock className="w-3 h-3 shrink-0 text-slate-500" />
                    <span className="truncate">{renderHighlightedText(item, value)}</span>
                  </div>

                  {isSelected && (
                    <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ── Quick Chips / Pills (Optional) ─────────────────────────────── */}
      {showChips && filteredSuggestions.length > 0 && !disabled && (
        <div className="flex items-center gap-1.5 flex-wrap mt-1.5 pt-1">
          <span className="text-[10px] text-slate-500 font-medium flex items-center gap-1">
            <Sparkles className="w-2.5 h-2.5 text-emerald-400" />
            Quick:
          </span>
          {filteredSuggestions.slice(0, 4).map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => handleSelect(chip)}
              className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/80 transition-all hover:border-emerald-500/40 active:scale-95 truncate max-w-[200px]"
              title={chip}
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {/* Error / Helper text */}
      {error ? (
        <p className="text-xs text-rose-400 mt-1">{error}</p>
      ) : helperText ? (
        <p className="text-xs text-slate-400 mt-1">{helperText}</p>
      ) : null}
    </div>
  );
};

export default AutoSuggestInput;
