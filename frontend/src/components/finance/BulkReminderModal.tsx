/**
 * US-C04: Broadcast Reminder Modal
 *
 * UI Fixes applied:
 *  1. Recipient count fetched live from /payments/campaigns/preview/ — no longer
 *     hardcoded from highRiskCount prop (which was escalation ≥ 3, not all-balance > 0).
 *  2. Segment selector exposed — Bursar can choose which group to target.
 *  3. Template placeholder style unified: shows {student_name} style (what the backend
 *     actually uses in .format()) alongside the bracket aliases the backend now bridges.
 *  4. Success screen shown before modal closes so the user gets confirmation.
 *  5. Duplicate-send guard: warns if a campaign was already dispatched today.
 *  6. Recipient preview list: shows sample students (masked phone) before dispatching.
 *  7. Dispatch button disabled when recipientCount = 0 (no one to message).
 */
import React, { useState, useEffect } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import {
  Send, Megaphone, Users, AlertCircle, CheckCircle2,
  ChevronDown, Eye, EyeOff, AlertTriangle, Clock,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

interface BulkReminderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSent?: (count: number) => void;
}

interface PreviewData {
  count: number;
  segment_type: string;
  sample: Array<{
    student_name: string;
    class_name: string;
    balance: number;
    guardian_phone: string;
  }>;
}

const SEGMENT_OPTIONS = [
  {
    value: 'all',
    label: 'All Defaulters',
    description: 'Every student with any outstanding balance this term',
  },
  {
    value: 'high_balance',
    label: 'High Balance (> UGX 500,000)',
    description: 'Critical accounts — highest priority for collection',
  },
  {
    value: 'medium_balance',
    label: 'Medium Balance (200k – 500k)',
    description: 'Moderate-risk accounts',
  },
  {
    value: 'low_balance',
    label: 'Low Balance (< UGX 200,000)',
    description: 'Near-cleared accounts — a final nudge',
  },
  {
    value: 'zero_payment',
    label: 'Zero Payment Made',
    description: 'Students who have not made any payment at all this term',
  },
  {
    value: 'partial_payment',
    label: 'Partial Payment Made',
    description: 'Students who paid something but still have a balance',
  },
];

// Default template uses {style} placeholders (what the backend .format() expects)
// The backend also accepts [Style] bracket tags — both are bridged automatically.
const DEFAULT_TEMPLATE =
  'Dear {parent_name}, your child {student_name} (Class {class_name}) has an outstanding fee balance of UGX {balance} at {school_name}. Please clear this by {deadline} to avoid disruption of studies. Thank you.';

const PLACEHOLDER_TAGS = [
  '{parent_name}',
  '{student_name}',
  '{balance}',
  '{class_name}',
  '{school_name}',
  '{deadline}',
];

interface TodayCampaignInfo {
  id: string;
  name: string;
  segment_type: string;
  segment_label: string;
  target_count: number;
  sent_count: number;
  status: string;
  dispatched_at: string;
}

interface TodayCampaignResponse {
  already_dispatched_today: boolean;
  count: number;
  last_campaign?: TodayCampaignInfo | null;
  campaigns?: TodayCampaignInfo[];
}

export const BulkReminderModal: React.FC<BulkReminderModalProps> = ({
  isOpen,
  onClose,
  onSent,
}) => {
  const queryClient = useQueryClient();
  const [segmentType, setSegmentType] = useState('all');
  const [template, setTemplate] = useState(DEFAULT_TEMPLATE);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [sentResult, setSentResult] = useState<{ count: number; name: string } | null>(null);
  const [quietHoursAcknowledged, setQuietHoursAcknowledged] = useState(false);
  const closeTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  // Uganda Messaging Window check (9:00 PM – 8:00 AM EAT, UTC+3)
  const isQuietHours = () => {
    const now = new Date();
    const eatHour = (now.getUTCHours() + 3) % 24;
    return eatHour >= 21 || eatHour < 8;
  };
  const quietHoursActive = isQuietHours();

  const handleClose = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setSentResult(null);
    setErrorMsg(null);
    setShowPreview(false);
    onClose();
  };

  // ── Authoritative duplicate check fetched live from backend ─────────────────
  const { data: todayData, refetch: refetchToday } = useQuery<TodayCampaignResponse>({
    queryKey: ['campaigns-today'],
    queryFn: async () => {
      const res = await apiClient.get('/payments/campaigns/today/');
      return res.data;
    },
    enabled: isOpen,
    staleTime: 0,
    refetchOnMount: 'always',
    networkMode: 'always',
    retry: 0,
  });

  const alreadySentToday = Boolean(todayData?.already_dispatched_today);

  // Reset local state whenever modal opens or closes
  useEffect(() => {
    if (!isOpen) {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
      setSentResult(null);
      setErrorMsg(null);
      setShowPreview(false);
      setQuietHoursAcknowledged(false);
    } else {
      setSentResult(null);
      setErrorMsg(null);
      setShowPreview(false);
      setQuietHoursAcknowledged(false);
      refetchToday();
    }
  }, [isOpen, refetchToday]);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  // ── Live recipient preview from backend ──────────────────────────────────────
  const {
    data: preview,
    isLoading: previewLoading,
    isFetching: previewFetching,
  } = useQuery<PreviewData>({
    queryKey: ['campaign-preview', segmentType],
    queryFn: async () => {
      const res = await apiClient.get('/payments/campaigns/preview/', {
        params: { segment_type: segmentType },
      });
      return res.data;
    },
    enabled: isOpen,
    staleTime: 60_000,
    networkMode: 'always',
    retry: 0,
  });

  const recipientCount = preview?.count ?? 0;

  // ── Mutation: create + launch campaign ──────────────────────────────────────
  const { mutate: launchCampaign, isPending } = useMutation({
    networkMode: 'always',
    retry: 0,
    mutationFn: async () => {
      setErrorMsg(null);
      const campaignName = `Fee Reminder – ${new Date().toLocaleDateString('en-UG', {
        day: '2-digit', month: 'short', year: 'numeric',
      })}`;

      const createRes = await apiClient.post('/payments/campaigns/', {
        name: campaignName,
        segment_type: segmentType,
        message_template_en: template,
      });

      const launchRes = await apiClient.post(
        `/payments/campaigns/${createRes.data.id}/launch/`,
      );

      return {
        count: launchRes.data.target_count ?? createRes.data.target_count ?? recipientCount,
        name: launchRes.data.name ?? campaignName,
      };
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['campaigns-today'] });
      queryClient.invalidateQueries({ queryKey: ['campaign-preview'] });
      setSentResult(result);
      onSent?.(result.count);
      closeTimerRef.current = setTimeout(() => {
        handleClose();
      }, 3500);
    },
    onError: (err: any) => {
      const data = err.response?.data;
      const msg =
        (typeof data?.detail === 'string' ? data.detail : null) ||
        (typeof data?.error === 'string' ? data.error : null) ||
        'Failed to dispatch broadcast campaign. Please check your connection and try again.';
      setErrorMsg(msg);
    },
  });

  // ── Success screen ───────────────────────────────────────────────────────────
  if (isOpen && sentResult) {
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Broadcast Reminders" maxWidth="md">
        <div className="flex flex-col items-center gap-5 py-8">
          <div className="p-4 bg-emerald-500/20 rounded-full animate-pulse">
            <CheckCircle2 className="w-12 h-12 text-emerald-400" />
          </div>
          <div className="text-center space-y-1">
            <p className="text-base font-bold text-white">Campaign Dispatched!</p>
            <p className="text-sm text-slate-300">
              <span className="font-semibold text-emerald-400">{sentResult.count}</span>{' '}
              personalised message{sentResult.count !== 1 ? 's' : ''} queued for delivery via
              WhatsApp/SMS.
            </p>
            <p className="text-xs text-slate-500 mt-2">Closing automatically…</p>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Button size="sm" variant="secondary" onClick={handleClose}>
              Close
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                if (closeTimerRef.current) {
                  clearTimeout(closeTimerRef.current);
                  closeTimerRef.current = null;
                }
                setSentResult(null);
                refetchToday();
              }}
              className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
            >
              Send Another Campaign
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  // ── Main modal ───────────────────────────────────────────────────────────────
  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Broadcast Reminders" maxWidth="lg">
      <div className="space-y-5">

        {/* Error banner */}
        {errorMsg && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-400 font-medium flex gap-2 items-start">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {errorMsg}
          </div>
        )}

        {/* Duplicate-send guard */}
        {alreadySentToday && (
          <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex gap-2.5 items-start">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
            <div className="space-y-1 flex-1">
              <p className="font-semibold text-amber-200">
                A campaign was already dispatched today. Sending again will create duplicate messages for the same parents.
              </p>
              {todayData?.last_campaign && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-amber-400/90 pt-0.5">
                  <span>
                    Last campaign: <strong className="text-amber-200 font-medium">&ldquo;{todayData.last_campaign.name}&rdquo;</strong>
                  </span>
                  <span>&middot;</span>
                  <span>Targeted: <strong className="text-amber-200">{todayData.last_campaign.target_count}</strong> {todayData.last_campaign.segment_label || todayData.last_campaign.segment_type}</span>
                  {todayData.last_campaign.dispatched_at && (
                    <>
                      <span>&middot;</span>
                      <span>Dispatched at: <strong className="text-amber-200">{new Date(todayData.last_campaign.dispatched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</strong></span>
                    </>
                  )}
                  {todayData.count > 1 && (
                    <span className="text-[10px] bg-amber-500/20 px-1.5 py-0.5 rounded text-amber-300 font-medium">
                      {todayData.count} total campaigns today
                    </span>
                  )}
                </div>
              )}
              <p className="text-[11px] text-amber-400/70 pt-0.5">
                You can still proceed if this is intentional (it is a warning, not a hard block).
              </p>
            </div>
          </div>
        )}

        {/* Uganda Messaging Quiet Hours Guard (9:00 PM – 8:00 AM EAT) */}
        {quietHoursActive && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex gap-2.5 items-start">
            <Clock className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
            <div className="space-y-1.5 flex-1">
              <p className="font-semibold text-amber-300">
                Uganda Messaging Quiet Hours Active (9:00 PM – 8:00 AM EAT)
              </p>
              <p className="text-amber-400/90 leading-relaxed text-[11px]">
                Sending broadcast reminders at night disturbs families and risks telecom carrier restrictions.
                Standard fee reminders should be sent during daytime hours (8:00 AM – 9:00 PM EAT).
              </p>
              <label className="flex items-center gap-2 pt-1 border-t border-amber-500/20 cursor-pointer">
                <input
                  type="checkbox"
                  checked={quietHoursAcknowledged}
                  onChange={(e) => setQuietHoursAcknowledged(e.target.checked)}
                  className="rounded border-amber-500/40 text-amber-500 focus:ring-amber-500 bg-slate-900"
                />
                <span className="text-[11px] font-medium text-amber-200">
                  Emergency override: I understand and confirm sending during quiet hours
                </span>
              </label>
            </div>
          </div>
        )}

        {/* Segment Selector */}
        <div className="space-y-1.5">
          <label className="text-xs font-bold text-slate-300 uppercase tracking-wider">
            Target Audience
          </label>
          <div className="relative">
            <select
              value={segmentType}
              onChange={(e) => {
                setSegmentType(e.target.value);
                setShowPreview(false);
              }}
              className="w-full appearance-none bg-slate-900 border border-slate-700 text-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 pr-9"
            >
              {SEGMENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          </div>
          <p className="text-[11px] text-slate-500">
            {SEGMENT_OPTIONS.find((o) => o.value === segmentType)?.description}
          </p>
        </div>

        {/* Live recipient count from backend */}
        <div className="p-4 bg-indigo-500/10 border border-indigo-500/20 rounded-xl flex gap-4 items-start">
          <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400 shrink-0">
            <Megaphone className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-indigo-300">
              {previewLoading || previewFetching
                ? 'Loading recipients…'
                : recipientCount === 0
                  ? 'No eligible recipients in this segment'
                  : `${recipientCount} guardian${recipientCount !== 1 ? 's' : ''} will receive this message`}
            </h3>
            <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 shrink-0" />
              Personalised per student · delivered via WhatsApp/SMS
            </p>
            {recipientCount > 0 && (
              <button
                className="text-xs text-indigo-400 hover:text-indigo-300 underline mt-2 transition-colors flex items-center gap-1"
                onClick={() => setShowPreview((v) => !v)}
              >
                {showPreview
                  ? <><EyeOff className="w-3 h-3" /> Hide preview</>
                  : <><Eye className="w-3 h-3" /> Preview recipients (first {Math.min(5, preview?.sample?.length ?? 0)} shown)</>}
              </button>
            )}
          </div>
        </div>

        {/* Recipient preview list */}
        {showPreview && preview?.sample && preview.sample.length > 0 && (
          <div className="bg-slate-900 border border-slate-700/60 rounded-xl overflow-hidden">
            <div className="px-3 py-2 bg-slate-800/60 border-b border-slate-700/60">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Sample Recipients — {preview.sample.length} of {recipientCount} shown
              </p>
            </div>
            <div className="divide-y divide-slate-800">
              {preview.sample.map((s, i) => (
                <div key={i} className="px-3 py-2.5 flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold text-slate-200">{s.student_name}</p>
                    <p className="text-[10px] text-slate-500">{s.class_name}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs font-semibold text-rose-400">
                      UGX {s.balance.toLocaleString()}
                    </p>
                    <p className="text-[10px] text-slate-500 font-mono">{s.guardian_phone}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Message template */}
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-300 uppercase tracking-wider">
            Message Template (English)
          </label>
          <textarea
            className="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-sm text-slate-200 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[120px] resize-y"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
          />
          <div className="p-2.5 bg-slate-800/50 rounded-lg border border-slate-700/60 space-y-1.5">
            <p className="text-[11px] text-slate-400 font-medium">
              Available placeholders — auto-replaced per student:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {PLACEHOLDER_TAGS.map((tag) => (
                <code
                  key={tag}
                  className="px-1.5 py-0.5 bg-slate-700 text-emerald-400 rounded text-[10px] font-mono cursor-pointer hover:bg-slate-600 transition-colors"
                  title="Click to insert"
                  onClick={() => setTemplate((t) => t + tag)}
                >
                  {tag}
                </code>
              ))}
            </div>
            <p className="text-[10px] text-slate-500">
              Both <code className="text-emerald-500">{'{student_name}'}</code> and{' '}
              <code className="text-emerald-500">[Student Name]</code> styles are accepted.
            </p>
          </div>
        </div>

        {/* Warning if no recipients */}
        {!previewLoading && !previewFetching && recipientCount === 0 && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-400 flex gap-2 items-start">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            No eligible recipients match this segment. No messages will be sent if you proceed.
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
          <Button variant="ghost" onClick={handleClose} disabled={isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => launchCampaign()}
            isLoading={isPending}
            disabled={isPending || recipientCount === 0 || (quietHoursActive && !quietHoursAcknowledged)}
            leftIcon={<Send className="w-4 h-4" />}
          >
            {recipientCount > 0
              ? `Dispatch to ${recipientCount} Guardian${recipientCount !== 1 ? 's' : ''}`
              : 'Dispatch Messages'}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
