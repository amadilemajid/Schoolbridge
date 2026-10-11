/**
 * Uganda Telecom Network Auto-Detection & Phone Validation Utility
 * Supports MTN Uganda and Airtel Uganda prefix matching and strict 10-digit validation:
 * - Local: 077..., 078..., 076..., 070..., 075..., 074..., 03..., 02... (Strictly 10 digits)
 * - International: +25677..., +25678..., +25676..., +25670..., +25675..., +25674..., +2563..., +2562... (Strictly +256 followed by 9 digits)
 */

export type TelecomProvider = 'mtn_momo' | 'airtel_money';

export interface TelecomNetworkInfo {
  provider: TelecomProvider;
  name: string;
  shortName: string;
  codePrompt: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  glowColor: string;
}

const MTN_INFO: TelecomNetworkInfo = {
  provider: 'mtn_momo',
  name: 'MTN Mobile Money',
  shortName: 'MTN MoMo',
  codePrompt: '*165# Prompt',
  badgeBg: 'bg-yellow-500/15',
  badgeText: 'text-yellow-400',
  badgeBorder: 'border-yellow-500/40',
  glowColor: 'shadow-yellow-950/40',
};

const AIRTEL_INFO: TelecomNetworkInfo = {
  provider: 'airtel_money',
  name: 'Airtel Money',
  shortName: 'Airtel Money',
  codePrompt: '*185# Prompt',
  badgeBg: 'bg-rose-500/15',
  badgeText: 'text-rose-400',
  badgeBorder: 'border-rose-500/40',
  glowColor: 'shadow-rose-950/40',
};

/**
 * Normalizes any phone string to clean local 10-digit format (07XXXXXXXX / 03XXXXXXXX)
 */
export const normalizeUgandaPhoneDigits = (rawPhone: string): string => {
  if (!rawPhone) return '';
  let cleaned = rawPhone.replace(/[^\d+]/g, '').trim();

  if (cleaned.startsWith('+256')) {
    cleaned = '0' + cleaned.slice(4);
  } else if (cleaned.startsWith('256')) {
    cleaned = '0' + cleaned.slice(3);
  } else if (cleaned.length === 9 && (cleaned.startsWith('7') || cleaned.startsWith('3') || cleaned.startsWith('2'))) {
    cleaned = '0' + cleaned;
  }

  return cleaned;
};

/**
 * Converts any valid Uganda phone to international standard +256XXXXXXXXX
 */
export const formatUgandaPhoneInternational = (rawPhone: string): string => {
  const local = normalizeUgandaPhoneDigits(rawPhone);
  if (local.startsWith('0') && local.length === 10) {
    return '+256' + local.slice(1);
  }
  return rawPhone.trim();
};

/**
 * Strict Phone Validation Result
 */
export interface PhoneValidationResult {
  isValid: boolean;
  normalized: string;
  international: string;
  provider: TelecomProvider | null;
  error?: string;
}

/**
 * Validates whether a phone number is a legitimate 10-digit Uganda number
 */
export const validateUgandaPhone = (rawPhone: string): PhoneValidationResult => {
  if (!rawPhone || !rawPhone.trim()) {
    return {
      isValid: false,
      normalized: '',
      international: '',
      provider: null,
      error: 'Phone number is required.',
    };
  }

  const digits = normalizeUgandaPhoneDigits(rawPhone);

  // Must only contain numeric digits after normalization
  if (!/^\d+$/.test(digits)) {
    return {
      isValid: false,
      normalized: digits,
      international: '',
      provider: null,
      error: 'Phone number must contain only numbers.',
    };
  }

  // Check exact 10 digits length for local format (e.g. 0771234567)
  if (digits.length < 10) {
    return {
      isValid: false,
      normalized: digits,
      international: '',
      provider: null,
      error: `Phone number is too short (${digits.length}/10 digits). Must be 10 digits (e.g. 0771234567).`,
    };
  }

  if (digits.length > 10) {
    return {
      isValid: false,
      normalized: digits,
      international: '',
      provider: null,
      error: `Phone number is too long (${digits.length}/10 digits). Must be 10 digits (e.g. 0771234567).`,
    };
  }

  // Must start with valid Uganda operator prefix (07X, 03X, 02X)
  const validPrefix = /^(07[0123456789]|03[129]|020)/.test(digits);
  if (!validPrefix) {
    return {
      isValid: false,
      normalized: digits,
      international: '',
      provider: null,
      error: 'Invalid Uganda prefix. Must start with 07X (MTN/Airtel), 03X (MTN Fixed), or 020 (Airtel Fixed).',
    };
  }

  const provider = detectUgandaTelecom(digits);
  const international = formatUgandaPhoneInternational(digits);

  return {
    isValid: true,
    normalized: digits,
    international,
    provider,
  };
};

/**
 * Detects whether a phone number belongs to MTN or Airtel
 */
export const detectUgandaTelecom = (phone: string): TelecomProvider | null => {
  const digits = normalizeUgandaPhoneDigits(phone);
  if (!digits || digits.length < 3) return null;

  // MTN Uganda Prefixes: 077, 078, 076, 031, 039, 032, 03
  const isMtn =
    digits.startsWith('077') ||
    digits.startsWith('078') ||
    digits.startsWith('076') ||
    digits.startsWith('031') ||
    digits.startsWith('039') ||
    digits.startsWith('032') ||
    digits.startsWith('03');

  if (isMtn) return 'mtn_momo';

  // Airtel Uganda Prefixes: 070, 075, 074, 020, 02
  const isAirtel =
    digits.startsWith('070') ||
    digits.startsWith('075') ||
    digits.startsWith('074') ||
    digits.startsWith('020') ||
    digits.startsWith('02');

  if (isAirtel) return 'airtel_money';

  return null;
};

/**
 * Returns UI metadata for the detected telecom provider
 */
export const getTelecomNetworkInfo = (phone: string): TelecomNetworkInfo | null => {
  const provider = detectUgandaTelecom(phone);
  if (provider === 'mtn_momo') return MTN_INFO;
  if (provider === 'airtel_money') return AIRTEL_INFO;
  return null;
};
