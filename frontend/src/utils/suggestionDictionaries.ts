import { apiClient } from '../api/client';

export type SuggestionCategory =
  | 'excused_reasons'
  | 'late_reasons'
  | 'absence_reasons'
  | 'attendance_notes'
  | 'academic_remarks'
  | 'rejection_reasons'
  | 'unlock_reasons'
  | 'waiver_reasons'
  | 'deactivation_reasons'
  | 'general';

/**
 * Standard Ugandan School Presets
 */
export const DOMAIN_PRESETS: Record<SuggestionCategory, string[]> = {
  excused_reasons: [
    'Parent called - family emergency',
    'Medical appointment / Clinic visit',
    'Sick with malaria / fever (Parent notified)',
    'Bereavement / Attending burial ceremony',
    'Authorized pass-out granted by Head Teacher',
    'Dental / Eye clinic checkup',
    'Floods / Impassable road after heavy rain',
    'School fee collection / Bank errand',
    'Official school sports / Music festival competition',
    'National ID / UNEB registration errand',
    'Religious observance / Holiday',
    'Transport breakdown on school van',
  ],
  late_reasons: [
    'Heavy morning rainfall / Road flooding',
    'Traffic congestion on main road',
    'Transport breakdown / Matatu delay',
    'Late walking from distant village',
    'Assisting guardian with urgent errand',
    'Delayed at clinic / Morning hospital visit',
    'Uniform / Scholastic materials preparation',
  ],
  absence_reasons: [
    'Sick - Malaria / Fever (No note yet)',
    'Unannounced absence - Parent phone unreachable',
    'Family emergency / Travel upcountry',
    'School fees balance follow-up',
    'Hospitalized / Under medical care',
    'Absent without official communication',
  ],
  attendance_notes: [
    'Parent notified via SMS / Phone call',
    'Clinic referral issued by nurse',
    'Disciplinary warning issued',
    'Special counseling required',
    'Scholastic assistance needed',
  ],
  academic_remarks: [
    'Excellent performance; keeps up the good work',
    'Shows great improvement; encouraged to participate more',
    'Capable of better results with increased focus',
    'Needs more practice in numerical problem solving',
    'Good effort; should concentrate on handwriting & presentation',
    'Very attentive and disciplined in class',
    'Active in group discussions and practical work',
  ],
  rejection_reasons: [
    'Marks entered exceed assessment paper maximum',
    'Missing scores for several enrolled candidates',
    'Grading scale or assessment weight mismatch',
    'Clerical calculation error detected in marks sheet',
    'Unapproved moderation adjustments submitted',
  ],
  unlock_reasons: [
    'Correction of teacher clerical entry typo approved by Director',
    'Audit reconciliation following paper remark request',
    'Late medical submission verified by administration',
  ],
  waiver_reasons: [
    'Director special scholarship discount',
    'Staff child tuition waiver',
    'Bursary awarded for sports / talent excellence',
    'Hardship relief approved by school board',
    'Sibling discount concession',
  ],
  deactivation_reasons: [
    'Transferred to another school (Relocation)',
    'Completed final examination candidate cycle',
    'Prolonged unannounced absence / Dropped out',
    'Medical withdrawal upon guardian request',
    'Financial hardship relocation',
  ],
  general: [
    'Approved by administration',
    'Follow-up pending',
    'Guardian contacted',
    'Special consideration granted',
  ],
};

const STORAGE_KEY_PREFIX = 'schoolbridge_suggest_history_';

/**
 * Get locally learned custom suggestions from localStorage
 */
export function getStoredCustomSuggestions(category: string): string[] {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY_PREFIX}${category}`);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch {
    // ignore JSON error
  }
  return [];
}

/**
 * Save user typed custom suggestion to localStorage for continuous learning
 */
export function saveStoredCustomSuggestion(category: string, text: string): void {
  const trimmed = text.trim();
  if (!trimmed || trimmed.length < 3) return;

  try {
    const existing = getStoredCustomSuggestions(category);
    // Move to front, deduplicate case-insensitively
    const filtered = existing.filter((item) => item.toLowerCase() !== trimmed.toLowerCase());
    const updated = [trimmed, ...filtered].slice(0, 25); // keep top 25 recent
    localStorage.setItem(`${STORAGE_KEY_PREFIX}${category}`, JSON.stringify(updated));
  } catch {
    // ignore storage error
  }
}

/**
 * Fetch suggestions: Queries live backend API, merges with client-learned history and presets
 */
export async function fetchCategorySuggestions(
  category: SuggestionCategory | string,
  query?: string
): Promise<string[]> {
  const custom = getStoredCustomSuggestions(category);
  const presets = DOMAIN_PRESETS[category as SuggestionCategory] || DOMAIN_PRESETS.general;

  try {
    const res = await apiClient.get('/automation/suggestions/', {
      params: {
        category,
        query: query?.trim() || undefined,
        limit: 20,
      },
    });

    const apiSuggestions: string[] = res.data?.suggestions || [];

    // Merge: custom learned first, then API returned (which includes DB historical records + domain presets)
    const combined: string[] = [];
    const seen = new Set<string>();

    // First filter custom learned that match query
    const qLower = (query || '').toLowerCase().trim();
    const matchingCustom = qLower
      ? custom.filter((item) => item.toLowerCase().includes(qLower))
      : custom;

    for (const item of [...matchingCustom, ...apiSuggestions, ...presets]) {
      const trimmed = item.trim();
      if (!trimmed) continue;
      const key = trimmed.toLowerCase();
      if (!seen.has(key)) {
        if (!qLower || key.includes(qLower)) {
          seen.add(key);
          combined.push(trimmed);
        }
      }
    }

    return combined.slice(0, 15);
  } catch (err) {
    console.warn('Failed to fetch API suggestions, using local fallback:', err);
    // Offline / fallback mode
    const qLower = (query || '').toLowerCase().trim();
    const combined = [...custom, ...presets];
    const seen = new Set<string>();
    const results: string[] = [];

    for (const item of combined) {
      const trimmed = item.trim();
      if (!trimmed) continue;
      const key = trimmed.toLowerCase();
      if (!seen.has(key)) {
        if (!qLower || key.includes(qLower)) {
          seen.add(key);
          results.push(trimmed);
        }
      }
    }

    return results.slice(0, 15);
  }
}
