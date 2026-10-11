import React, { forwardRef } from 'react';
import { TextInput } from './TextInput';
import { Phone } from 'lucide-react';
import { getTelecomNetworkInfo } from '../../utils/telecom';

interface UgandaPhoneInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  showNetworkBadge?: boolean;
  onNetworkDetected?: (provider: 'mtn_momo' | 'airtel_money') => void;
}

export const UgandaPhoneInput = forwardRef<HTMLInputElement, UgandaPhoneInputProps>(({
  label = 'Ugandan Phone Number',
  error,
  helperText = 'e.g. 0771234567 or +256771234567',
  showNetworkBadge = true,
  onNetworkDetected,
  value,
  onChange,
  ...props
}, ref) => {
  const phoneStr = String(value || '');
  const network = showNetworkBadge ? getTelecomNetworkInfo(phoneStr) : null;

  React.useEffect(() => {
    if (network && onNetworkDetected) {
      onNetworkDetected(network.provider);
    }
  }, [network?.provider, onNetworkDetected]);

  return (
    <div className="w-full flex flex-col gap-1.5">
      {label ? (
        <div className="flex items-center justify-between min-h-[22px]">
          <label className="text-sm font-medium text-slate-300">
            {label}
          </label>
          {network && (
            <div
              className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold border transition-all animate-fadeIn ${network.badgeBg} ${network.badgeText} ${network.badgeBorder}`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              {network.name || network.shortName}
            </div>
          )}
        </div>
      ) : network ? (
        <div className="flex justify-end">
          <div
            className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold border transition-all animate-fadeIn ${network.badgeBg} ${network.badgeText} ${network.badgeBorder}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            {network.name || network.shortName}
          </div>
        </div>
      ) : null}

      <TextInput
        ref={ref}
        error={error}
        helperText={helperText}
        placeholder="0771234567"
        type="tel"
        leftIcon={<Phone className="w-4 h-4 text-emerald-400" />}
        value={value}
        onChange={onChange}
        {...props}
      />
    </div>
  );
});

UgandaPhoneInput.displayName = 'UgandaPhoneInput';
