import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { AutoSuggestInput } from '../ui/AutoSuggestInput';
import { CurrencyInput } from '../ui/CurrencyInput';
import { Select } from '../ui/Select';
import { ShieldCheck, AlertCircle, CheckCircle2, AlertTriangle } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

interface ApplyWaiverModalProps {
  isOpen: boolean;
  onClose: () => void;
  feeRecordId: string;
  studentCode?: string;
  className?: string;
  studentName: string;
  totalAmount: number;
  amountPaid?: number;
  amountWaived?: number;
  balance: number;
  isDirector?: boolean;
  onWaiverApplied?: (feeRecordId: string, amount: number) => void;
}

const DEFAULT_WAIVER_REASONS = [
  { value: 'academic_scholarship', label: 'Academic Scholarship' },
  { value: 'staff_child_discount', label: 'Staff Child Discount' },
  { value: 'sibling_discount', label: 'Sibling Discount' },
  { value: 'orphan_bursary', label: 'Orphan / Vulnerability Bursary' },
  { value: 'sports_scholarship', label: 'Sports Scholarship' },
  { value: 'partial_payment_agreement', label: 'Partial Payment Agreement' },
  { value: 'other', label: 'Other (specify below)' },
];

export const ApplyWaiverModal: React.FC<ApplyWaiverModalProps> = ({
  isOpen,
  onClose,
  feeRecordId,
  studentCode,
  className,
  studentName,
  totalAmount,
  amountPaid = 0,
  amountWaived = 0,
  balance,
  isDirector = false,
  onWaiverApplied,
}) => {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState<number | ''>('');
  const [reason, setReason] = useState('');
  const [reasonDetail, setReasonDetail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<{ status: string; amount: number } | null>(null);

  // Fetch dynamic waiver reason categories from backend metadata
  const { data: metadata } = useQuery({
    queryKey: ['system-metadata'],
    queryFn: async () => {
      const res = await apiClient.get('/schools/metadata/');
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const waiverReasons: Array<{ value: string; label: string }> =
    metadata?.waiver_reasons && Array.isArray(metadata.waiver_reasons) && metadata.waiver_reasons.length > 0
      ? metadata.waiver_reasons
      : DEFAULT_WAIVER_REASONS;

  const waiverAmount = typeof amount === 'number' ? amount : (parseInt(String(amount).replace(/,/g, ''), 10) || 0);
  const currentBalance = Math.max(0, balance);
  const maxWaiver = currentBalance;
  const isZeroBalance = currentBalance <= 0;

  const isAmountValid = waiverAmount > 0 && waiverAmount <= maxWaiver;
  const isReasonValid = Boolean(reason && (reason !== 'other' || (reasonDetail && reasonDetail.trim().length >= 3)));
  const isValid = isAmountValid && isReasonValid && !isZeroBalance;

  const { mutate: submitWaiver, isPending } = useMutation({
    mutationFn: async () => {
      const fullReason =
        reason === 'other'
          ? reasonDetail.trim()
          : waiverReasons.find((r) => r.value === reason)?.label || reason;
      const res = await apiClient.post('/payments/waivers/', {
        fee_record_id: feeRecordId,
        amount: waiverAmount,
        reason: fullReason,
      });
      return res.data;
    },
    onSuccess: (data: any) => {
      if (onWaiverApplied) onWaiverApplied(feeRecordId, waiverAmount);
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.refetchQueries({ queryKey: ['fee-records'] });
      queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
      queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
      queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
      setSubmitted({ status: data?.status || 'pending', amount: waiverAmount });
      // Auto-close after 3.5 seconds
      setTimeout(() => {
        setSubmitted(null);
        setAmount('');
        setReason('');
        setReasonDetail('');
        onClose();
      }, 3500);
    },
    onError: (err: any) => {
      if (!err.response) {
        setError('Connection error: Unable to reach the server. Please check your network and try again.');
        return;
      }
      const data = err.response?.data;
      const detail = data?.detail ?? data?.error ?? data?.message ?? data;
      const msg = typeof detail === 'string'
        ? detail
        : typeof detail === 'object' && detail !== null
          ? Object.entries(detail).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' • ')
          : 'Failed to submit waiver request. Please try again.';
      setError(msg || 'Failed to submit waiver request. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!isValid) return;
    submitWaiver();
  };

  const handleClose = () => {
    setSubmitted(null);
    setAmount('');
    setReason('');
    setReasonDetail('');
    setError(null);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isDirector ? 'Grant Fee Discount / Bursary' : 'Request Fee Discount / Bursary'}
      maxWidth="md"
    >
      {/* ── Success confirmation screen ── */}
      {submitted ? (
        <div className="flex flex-col items-center text-center gap-5 py-6 px-4">
          {submitted.status === 'approved' ? (
            <>
              <div className="p-4 rounded-full bg-emerald-500/15 border border-emerald-500/30">
                <CheckCircle2 className="w-10 h-10 text-emerald-400" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white mb-1">Waiver Applied Successfully</h3>
                <p className="text-sm text-slate-300">
                  <span className="text-emerald-400 font-semibold">UGX {submitted.amount.toLocaleString()}</span> has been
                  credited to <span className="text-white font-semibold">{studentName}</span>'s account
                  with <span className="text-emerald-400 font-semibold">immediate effect</span>.
                </p>
                <p className="text-xs text-slate-400 mt-2">The student's fee balance has been updated in real-time.</p>
              </div>
            </>
          ) : (
            <>
              <div className="p-4 rounded-full bg-amber-500/15 border border-amber-500/30">
                <ShieldCheck className="w-10 h-10 text-amber-400" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white mb-1">Waiver Request Submitted</h3>
                <p className="text-sm text-slate-300">
                  A waiver request of <span className="text-amber-400 font-semibold">UGX {submitted.amount.toLocaleString()}</span> for{' '}
                  <span className="text-white font-semibold">{studentName}</span> has been logged.
                </p>
                <div className="mt-4 p-3.5 bg-amber-500/10 border border-amber-500/25 rounded-xl text-xs text-amber-300 space-y-1.5">
                  <p className="font-semibold flex items-center gap-1.5 justify-center">
                    <ShieldCheck className="w-4 h-4 shrink-0" />
                    Awaiting Director Authorization
                  </p>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    This discount will <strong className="text-white font-semibold">not</strong> take effect until
                    the Director reviews and authorizes it. The student's account now displays the status{' '}
                    <span className="text-amber-400 font-semibold font-mono">"Pending Approval"</span>.
                  </p>
                </div>
                <p className="text-[11px] text-slate-500 mt-3">Window will close automatically…</p>
              </div>
            </>
          )}
          <Button variant="ghost" size="sm" onClick={handleClose} className="text-xs">
            Close
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Role-aware authorization banner */}
          {isDirector ? (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex gap-3.5 items-start">
              <div className="p-2 bg-emerald-500/20 rounded-lg text-emerald-400 shrink-0">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-emerald-400">Director Direct Authorization</h3>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  As Director, granting this discount updates the student's balance{' '}
                  <strong className="text-white">immediately</strong> without an approval waiting queue.
                </p>
              </div>
            </div>
          ) : (
            <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex gap-3.5 items-start">
              <div className="p-2 bg-amber-500/20 rounded-lg text-amber-400 shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-amber-400">Awaits Director Authorization</h3>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  Bursar submissions are routed to the Director's Approval Queue. The student's fee balance{' '}
                  <strong className="text-white">remains unchanged</strong> until authorized.
                </p>
              </div>
            </div>
          )}

          {/* Student Financial Breakdown Card */}
          <div className="p-4 bg-slate-900/90 rounded-xl border border-slate-800 space-y-3">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Student Account</p>
                <h4 className="text-sm font-bold text-white">{studentName}</h4>
                <p className="text-[11px] font-mono text-emerald-400 mt-0.5">
                  {studentCode} {className ? `• ${className}` : ''}
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Outstanding Balance</p>
                <p className={`text-sm font-mono font-bold ${currentBalance > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  UGX {currentBalance.toLocaleString()}
                </p>
              </div>
            </div>

            <div className={`grid ${amountWaived > 0 ? 'grid-cols-4' : 'grid-cols-3'} gap-2 pt-2 border-t border-slate-800/80 text-center`}>
              <div className="bg-slate-800/60 rounded-lg p-2">
                <span className="text-[10px] text-slate-400 block">Total Billed</span>
                <span className="text-xs font-mono font-semibold text-slate-200">UGX {totalAmount.toLocaleString()}</span>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-2">
                <span className="text-[10px] text-slate-400 block">Paid to Date</span>
                <span className="text-xs font-mono font-semibold text-emerald-400">UGX {amountPaid.toLocaleString()}</span>
              </div>
              {amountWaived > 0 && (
                <div className="bg-slate-800/60 rounded-lg p-2">
                  <span className="text-[10px] text-slate-400 block">Prev Waived</span>
                  <span className="text-xs font-mono font-semibold text-indigo-400">UGX {amountWaived.toLocaleString()}</span>
                </div>
              )}
              <div className="bg-slate-800/60 rounded-lg p-2">
                <span className="text-[10px] text-slate-400 block">Max Allowable</span>
                <span className="text-xs font-mono font-semibold text-indigo-300">UGX {maxWaiver.toLocaleString()}</span>
              </div>
            </div>
          </div>

          {/* Zero balance warning banner */}
          {isZeroBalance && (
            <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl flex gap-2.5 text-rose-300 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
              <span>
                <strong>Zero Balance:</strong> This student fee account has no outstanding balance (UGX 0).
                A waiver or bursary discount cannot be applied to an already cleared account.
              </span>
            </div>
          )}

          {error && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl flex gap-2 text-rose-400 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <CurrencyInput
            label="Discount / Waiver Amount (UGX)"
            placeholder="e.g. 50,000"
            value={amount}
            onChange={(val) => setAmount(val)}
            required
            disabled={isZeroBalance}
            helperText={
              amount !== '' && waiverAmount > maxWaiver
                ? `Cannot exceed outstanding balance: UGX ${maxWaiver.toLocaleString()} (Total fees: UGX ${totalAmount.toLocaleString()}, Paid: UGX ${amountPaid.toLocaleString()})`
                : waiverAmount > 0
                  ? isDirector
                    ? `UGX ${waiverAmount.toLocaleString()} will be credited immediately to student balance`
                    : `UGX ${waiverAmount.toLocaleString()} will be submitted to Director for authorization`
                  : `Enter amount in UGX (Maximum allowable: UGX ${maxWaiver.toLocaleString()})`
            }
          />

          <Select
            label="Reason Category"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            disabled={isZeroBalance}
            options={[{ value: '', label: 'Select a reason category…' }, ...waiverReasons]}
          />

          {reason === 'other' && (
            <AutoSuggestInput
              label="Specify Custom Reason"
              placeholder="e.g. Orphan scholarship / Church bursary..."
              value={reasonDetail}
              onChange={setReasonDetail}
              category="waiver_reasons"
              showChips={true}
            />
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button variant="ghost" onClick={handleClose} disabled={isPending} type="button">
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              isLoading={isPending}
              disabled={!isValid}
              leftIcon={
                isDirector ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : (
                  <ShieldCheck className="w-4 h-4" />
                )
              }
            >
              {isDirector ? 'Grant Waiver Directly' : 'Submit Waiver Request'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
};
