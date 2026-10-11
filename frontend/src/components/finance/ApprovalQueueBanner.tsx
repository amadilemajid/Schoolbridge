import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Button } from '../ui/Button';
import {
  ShieldAlert, CheckCircle2, Clock, User, Tag, Sparkles,
  X, AlertCircle, BookOpen,
} from 'lucide-react';

interface ApprovalQueueBannerProps {
  isDirector: boolean;
  onPaymentApproved?: (studentName: string, amount: number) => void;
  onWaiverApproved?: (studentName: string, amount: number) => void;
  onOpenWaiversModal?: () => void;
}

export const ApprovalQueueBanner: React.FC<ApprovalQueueBannerProps> = ({
  isDirector,
  onPaymentApproved,
  onWaiverApproved,
  onOpenWaiversModal,
}) => {
  const queryClient = useQueryClient();

  // Track which waiver is in inline-reject mode
  const [rejectingWaiverId, setRejectingWaiverId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [approvingPaymentId, setApprovingPaymentId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // ── Fetch pending payments ────────────────────────────────────────────────
  const { data: pendingPayments = [], isLoading: loadingPayments } = useQuery<any[]>({
    queryKey: ['pending-payments-queue'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/payments/payments/', { params: { status: 'pending' } });
        const raw = res.data?.results || res.data || [];
        return Array.isArray(raw) ? raw.filter((p: any) => p.status === 'pending') : [];
      } catch {
        return [];
      }
    },
    enabled: isDirector,
    refetchInterval: 15000,
  });

  // ── Fetch pending waivers ─────────────────────────────────────────────────
  const { data: pendingWaivers = [], isLoading: loadingWaivers } = useQuery<any[]>({
    queryKey: ['approval-queue-waivers'],
    queryFn: async () => {
      try {
        // Filter at server level — only pending waivers
        const res = await apiClient.get('/payments/waivers/', {
          params: { status: 'pending', page_size: 50 },
        });
        const raw = res.data?.results || res.data || [];
        return Array.isArray(raw) ? raw.filter((w: any) => w.status === 'pending') : [];
      } catch {
        return [];
      }
    },
    enabled: isDirector,
    refetchInterval: 15000,
  });

  // ── Approve payment ───────────────────────────────────────────────────────
  const { mutate: approvePayment, isPending: isApprovingPayment } = useMutation({
    mutationFn: async (payment: any) => {
      setApprovingPaymentId(payment.id);
      setActionError(null);
      const res = await apiClient.post(`/payments/payments/${payment.id}/approve/`);
      return { payment, data: res.data };
    },
    onSuccess: ({ payment }) => {
      setApprovingPaymentId(null);
      setSuccessMsg(`✅ Payment of UGX ${Number(payment.amount).toLocaleString()} for ${payment.student_name || 'Student'} approved.`);
      setTimeout(() => setSuccessMsg(null), 5000);
      queryClient.invalidateQueries({ queryKey: ['pending-payments-queue'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.refetchQueries({ queryKey: ['fee-records'] });
      queryClient.invalidateQueries({ queryKey: ['student-payments'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
      if (onPaymentApproved) onPaymentApproved(payment.student_name || 'Student', Number(payment.amount));
    },
    onError: (err: any) => {
      setApprovingPaymentId(null);
      const raw = err.response?.data;
      const msg: string =
        (typeof raw?.error === 'string' ? raw.error : null) ||
        (typeof raw?.detail === 'string' ? raw.detail : null) ||
        (Array.isArray(raw?.non_field_errors) ? raw.non_field_errors[0] : null) ||
        'Failed to approve payment.';
      setActionError(msg);
    },
  });

  // ── Approve waiver ────────────────────────────────────────────────────────
  const { mutate: approveWaiver, isPending: isApprovingWaiver, variables: approvingWaiverVar } = useMutation({
    mutationFn: async (waiver: any) => {
      setActionError(null);
      const res = await apiClient.post(`/payments/waivers/${waiver.id}/approve/`);
      return { waiver, data: res.data };
    },
    onSuccess: ({ waiver }) => {
      const amount = Number(waiver.amount);
      setSuccessMsg(`✅ Waiver of UGX ${amount.toLocaleString()} for ${waiver.student_name || 'Student'} approved and applied to their balance.`);
      setTimeout(() => setSuccessMsg(null), 5000);
      queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
      queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
      queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.refetchQueries({ queryKey: ['fee-records'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
      if (onWaiverApproved) onWaiverApproved(waiver.student_name || 'Student', amount);
    },
    onError: (err: any) => {
      const raw = err.response?.data;
      const msg: string =
        (typeof raw?.error === 'string' ? raw.error : null) ||
        (typeof raw?.detail === 'string' ? raw.detail : null) ||
        'Failed to approve waiver.';
      setActionError(msg);
    },
  });

  // ── Reject waiver (inline) ────────────────────────────────────────────────
  const { mutate: rejectWaiver, isPending: isRejectingWaiver, variables: rejectingWaiverVar } = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
      setActionError(null);
      const res = await apiClient.post(`/payments/waivers/${id}/reject/`, { reason });
      return { id, reason, data: res.data };
    },
    onSuccess: ({ data }) => {
      setRejectingWaiverId(null);
      setRejectReason('');
      setSuccessMsg(data?.message || '✅ Waiver request rejected successfully.');
      setTimeout(() => setSuccessMsg(null), 5000);
      queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
      queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
      queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
    },
    onError: (err: any) => {
      const raw = err.response?.data;
      const msg: string =
        (typeof raw?.error === 'string' ? raw.error : null) ||
        (typeof raw?.detail === 'string' ? raw.detail : null) ||
        'Failed to reject waiver.';
      setActionError(msg);
    },
  });

  const handleConfirmReject = (waiverId: string) => {
    if (!rejectReason.trim() || rejectReason.trim().length < 5) {
      setActionError('Rejection reason must be at least 5 characters.');
      return;
    }
    rejectWaiver({ id: waiverId, reason: rejectReason.trim() });
  };

  if (!isDirector) return null;

  const totalPending = pendingPayments.length + pendingWaivers.length;
  if (totalPending === 0 && !loadingPayments && !loadingWaivers) return null;

  return (
    <div className="bg-amber-950/40 border border-amber-500/40 rounded-2xl p-5 shadow-2xl space-y-4 animate-in fade-in-50 duration-300">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-amber-500/20 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-amber-200 tracking-tight flex items-center gap-2">
              Director Authorization Queue
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                {totalPending} Action{totalPending !== 1 ? 's' : ''} Required
              </span>
            </h3>
            <p className="text-[11px] text-amber-300/70 mt-0.5">
              Fee waivers and high-value payments (&gt; UGX 500,000) require Director sign-off before being credited to student balances.
            </p>
          </div>
        </div>

        {pendingWaivers.length > 0 && onOpenWaiversModal && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenWaiversModal}
            className="text-xs border-amber-500/40 text-amber-300 hover:bg-amber-500/20 shrink-0"
          >
            <BookOpen className="w-3.5 h-3.5 mr-1.5" />
            Review All {pendingWaivers.length} Waiver{pendingWaivers.length > 1 ? 's' : ''}
          </Button>
        )}
      </div>

      {/* ── Success / Error Feedback ── */}
      {successMsg && (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
          {successMsg}
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 text-rose-400" />
          {actionError}
          <button onClick={() => setActionError(null)} className="ml-auto opacity-60 hover:opacity-100">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* ── Pending Waivers ── */}
      {pendingWaivers.length > 0 && (
        <div className="space-y-2.5">
          <div className="text-[11px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Fee Waivers & Bursaries Awaiting Authorization ({pendingWaivers.length})</span>
          </div>

          <div className="grid gap-2.5">
            {pendingWaivers.map((w) => {
              const amountNum = Number(w.amount) || 0;
              const isThisApproving = isApprovingWaiver && (approvingWaiverVar as any)?.id === w.id;
              const isThisRejecting = isRejectingWaiver && (rejectingWaiverVar as any)?.id === w.id;
              const showRejectForm = rejectingWaiverId === w.id;

              return (
                <div
                  key={w.id}
                  className="bg-slate-900/80 border border-amber-500/30 rounded-xl overflow-hidden hover:border-amber-400/50 transition-colors"
                >
                  {/* Card body */}
                  <div className="p-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shrink-0 mt-0.5">
                        <Clock className="w-4 h-4" />
                      </div>
                      <div>
                        {/* Student name + ID + class + status badge */}
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-sm font-bold text-white tracking-tight">
                            {w.student_name || 'Student'}
                          </h4>
                          {w.student_id_code && (
                            <span className="font-mono text-[10px] text-emerald-400 font-semibold bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                              {w.student_id_code}
                            </span>
                          )}
                          {w.class_name && (
                            <span className="text-[10px] text-slate-400 font-medium">· {w.class_name}</span>
                          )}
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                            <Clock className="w-2.5 h-2.5" /> Status: Pending
                          </span>
                        </div>

                        {/* Amount + reason + requester */}
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-slate-400">
                          <span>
                            Waiver amount:{' '}
                            <strong className="text-amber-300 font-mono font-bold">
                              UGX {amountNum.toLocaleString()}
                            </strong>
                          </span>
                          <span>&bull;</span>
                          <span>
                            Reason: <strong className="text-slate-200">{w.reason}</strong>
                          </span>
                          {w.requested_by_name && (
                            <>
                              <span>&bull;</span>
                              <span className="flex items-center gap-1">
                                <User className="w-3 h-3 text-slate-500" />
                                Requested by: {w.requested_by_name}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Action buttons — only shown when NOT in reject form */}
                    {!showRejectForm && (
                      <div className="flex items-center gap-2 self-end md:self-auto shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setRejectingWaiverId(w.id);
                            setRejectReason('');
                            setActionError(null);
                          }}
                          disabled={isThisApproving || isThisRejecting}
                          className="text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 border border-rose-500/20 px-3"
                        >
                          <X className="w-3 h-3 mr-1" /> Reject
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => approveWaiver(w)}
                          isLoading={isThisApproving}
                          disabled={isThisApproving || isThisRejecting}
                          leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                          className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-950/40 text-xs font-semibold px-4"
                        >
                          Approve (UGX {amountNum.toLocaleString()})
                        </Button>
                      </div>
                    )}
                  </div>

                  {/* Inline reject form — expands below the card */}
                  {showRejectForm && (
                    <div className="px-3.5 pb-3.5 border-t border-rose-500/20 bg-rose-950/20 space-y-2.5 pt-3">
                      <p className="text-xs font-semibold text-rose-300 flex items-center gap-1.5">
                        <X className="w-3.5 h-3.5 shrink-0" />
                        Reject waiver for <strong>{w.student_name}</strong> — provide reason:
                      </p>
                      <input
                        type="text"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="e.g. Does not meet bursary eligibility criteria..."
                        className="w-full bg-slate-900 border border-rose-500/30 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-rose-500/50"
                        autoFocus
                      />
                      <div className="flex items-center gap-2 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[11px] text-slate-400"
                          onClick={() => { setRejectingWaiverId(null); setRejectReason(''); setActionError(null); }}
                          disabled={isThisRejecting}
                        >
                          Cancel
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          className="text-[11px]"
                          isLoading={isThisRejecting}
                          onClick={() => handleConfirmReject(w.id)}
                          disabled={!rejectReason.trim() || rejectReason.trim().length < 5 || isThisRejecting}
                        >
                          Confirm Rejection
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Pending High-Value Payments ── */}
      {pendingPayments.length > 0 && (
        <div className="space-y-2.5">
          <div className="text-[11px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
            <Tag className="w-3 h-3" />
            <span>Large Payments Awaiting Authorization ({pendingPayments.length})</span>
          </div>

          <div className="grid gap-2.5">
            {pendingPayments.map((p) => {
              const amountNum = Number(p.amount) || 0;
              const isCurrentApproving = approvingPaymentId === p.id;

              return (
                <div
                  key={p.id}
                  className="bg-slate-900/80 border border-amber-500/30 rounded-xl p-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-3 hover:border-amber-400/50 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shrink-0 mt-0.5">
                      <Clock className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-bold text-white tracking-tight">
                          {p.student_name || 'Student'}
                        </h4>
                        {p.student_id_code && (
                          <span className="font-mono text-[10px] text-emerald-400 font-semibold bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                            {p.student_id_code}
                          </span>
                        )}
                        {p.class_name && (
                          <span className="text-[10px] text-slate-400 font-medium">· {p.class_name}</span>
                        )}
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          <Clock className="w-2.5 h-2.5" /> Status: Pending
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-slate-400">
                        <span>
                          Amount:{' '}
                          <strong className="text-emerald-400 font-mono font-bold">
                            UGX {amountNum.toLocaleString()}
                          </strong>
                        </span>
                        <span>&bull;</span>
                        <span>
                          Method: <strong className="text-slate-200 capitalize">{p.method?.replace(/_/g, ' ')}</strong>
                        </span>
                        <span>&bull;</span>
                        <span className="flex items-center gap-1">
                          <User className="w-3 h-3 text-slate-500" />
                          <span>Cashier: {p.recorded_by_name || 'Bursar'}</span>
                        </span>
                        {p.receipt_number && (
                          <>
                            <span>&bull;</span>
                            <span className="font-mono text-[11px] text-slate-400">Ref: {p.receipt_number}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-end md:self-auto shrink-0">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => approvePayment(p)}
                      isLoading={isCurrentApproving || isApprovingPayment}
                      leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-950/40 text-xs font-semibold px-4"
                    >
                      Approve Payment (UGX {amountNum.toLocaleString()})
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
