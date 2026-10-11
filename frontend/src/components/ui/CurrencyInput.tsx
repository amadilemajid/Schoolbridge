import React, { forwardRef, useState } from 'react';
import { TextInput } from './TextInput';
import { Banknote } from 'lucide-react';

interface CurrencyInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> {
  label?: string;
  value: number | string;
  onChange: (val: number) => void;
  error?: string;
  helperText?: string;
  currencyPrefix?: string;
}

export const CurrencyInput = forwardRef<HTMLInputElement, CurrencyInputProps>(({
  label = 'Amount (UGX)',
  value,
  onChange,
  error,
  helperText = 'Amounts are formatted in Ugandan Shillings (UGX)',
  currencyPrefix = 'UGX',
  placeholder = '0',
  ...props
}, ref) => {
  const [inputNote, setInputNote] = useState<string | null>(null);

  const numericValue = typeof value === 'number' ? value : (value === '' ? '' : Number(value));
  const formattedDisplay = numericValue === '' || isNaN(numericValue as number) ? '' : (numericValue as number).toLocaleString('en-US');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawInput = e.target.value;
    // Detect if user tried to enter invalid chars (letters, symbols, negative)
    if (rawInput !== '' && /[^0-9,]/.test(rawInput)) {
      if (rawInput.includes('-')) {
        setInputNote('Negative amounts are not allowed. Enter a positive value only.');
      } else {
        setInputNote('Only numeric digits are accepted. Letters and symbols are not allowed.');
      }
      setTimeout(() => setInputNote(null), 3000);
    } else {
      setInputNote(null);
    }
    const raw = rawInput.replace(/,/g, '').replace(/[^0-9]/g, '');
    const num = raw ? parseInt(raw, 10) : 0;
    onChange(num);
  };

  const displayHelperText = inputNote || helperText;
  const helperColor = inputNote ? 'text-amber-400' : undefined;

  return (
    <TextInput
      ref={ref}
      label={label}
      error={error}
      helperText={displayHelperText}
      helperTextClassName={helperColor}
      placeholder={placeholder}
      value={formattedDisplay}
      onChange={handleChange}
      leftIcon={<Banknote className="w-4 h-4 text-emerald-400" />}
      rightIcon={<span className="text-xs font-bold text-slate-400 select-none">{currencyPrefix}</span>}
      inputMode="numeric"
      autoComplete="off"
      {...props}
    />
  );
});

CurrencyInput.displayName = 'CurrencyInput';
