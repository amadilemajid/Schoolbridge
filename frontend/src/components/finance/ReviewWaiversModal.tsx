import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Check, X, ShieldCheck, Clock, User, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';

interface WaiverItem {
  id: string;
  student_name: string;
  student_id_code: string;
  amount: number | string;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
  requested_by_name?: string;
  approved_by_name?: string;
  rejected_by_name?: string;
  rejection_reason?: string;
  created_at: string;
}

interface ReviewWaiversModalProps {
  isOpen: boolean;
  onClose: () => void;
  isDirector: boolean;
  highlightStudentName?: string;
  onWaiverApproved?: (message: string) => void;
}

export const ReviewWaiversModal: React.FC<ReviewWaiversModalProps> = ({
  isOpen,
  onClose,
  isDirector,
  highlightStudentName,
  onWaiverApproved,
}) => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const { data: waivers = [], isLoading } = useQuery<WaiverItem[]>({
    queryKey: ['fee-waivers-review'],
    queryFn: async () => {
      try {
        // Fetch pending waivers first (for the approval queue)
        const [pendingRes, historyRes] = await Promise.all([
          apiClient.get('/payments/waivers/', { params: { status: 'pending', page_size: 100 } }),
          apiClient.get('/payments/waivers/', { params: { page_size: 20, ordering: '-created_at' } }),
        ]);
        const pending: any[] = pendingRes.data?.results || pendingRes.data || [];
        const history: any[] = historyRes.data?.results || historyRes.data || [];
        // Merge: pending first, then recent non-pending (deduplicated by id)
        const seen = new Set(pending.map((w: any) => w.id));
        const combined = [
          ...pending,
          ...history.filter((w: any) => !seen.has(w.id)),
        ];
        return Array.isArray(combined) ? combined : [];
      } catch {
        return [];
      }
    },
    enabled: isOpen,
    refetchInterval: isOpen ? 10000 : false,
  });


  const { mutate: approveWaiver, isPending: isApproving } = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiClient.post(`/payments/waivers/${id}/approve/`);
      return res.data;
    },
    onSuccess: (data: any) => {
      const msg = data?.message || 'Waiver approved successfully! Student balance has been updated.';
      setActionError(null);
      setActionSuccess(msg);
      if (onWaiverApproved) onWaiverApproved(msg);
      queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
      queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
      queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.refetchQueries({ queryKey: ['fee-records'] });
      setTimeout(() => setActionSuccess(null), 6000);
    },
    onError: (err: any) => {
      setActionSuccess(null);
      const raw = err.response?.data;
      const msg: string =
        (typeof raw?.error === 'string' ? raw.error : null) ||
        (typeof raw?.detail === 'string' ? raw.detail : null) ||
        'Failed to approve waiver.';
      setActionError(msg);
    }
  });

  const { mutate: rejectWaiver, isPending: isRejecting } = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
      const res = await apiClient.post(`/payments/waivers/${id}/reject/`, { reason });
      return res.data;
    },
    onSuccess: (data: any) => {
      setActionError(null);
      setRejectingId(null);
      setRejectReason('');
      setActionSuccess(data?.message || 'Waiver request rejected.');
      queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
      queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
      queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      setTimeout(() => setActionSuccess(null), 6000);
    },
    onError: (err: any) => {
      setActionSuccess(null);
      const raw = err.response?.data;
      const msg: string =
        (typeof raw?.error === 'string' ? raw.error : null) ||
        (typeof raw?.detail === 'string' ? raw.detail : null) ||
        'Failed to reject waiver.';
      setActionError(msg);
    }
  });

  const handleStartReject = (id: string) => {
    setRejectingId(id);
    setRejectReason('');
    setActionError(null);
    setActionSuccess(null);
  };

  const handleConfirmReject = (id: string) => {
    if (!rejectReason.trim() || rejectReason.trim().length < 5) {
      setActionError('Please provide a valid rejection reason (min 5 characters).');
      return;
    }
    rejectWaiver({ id, reason: rejectReason.trim() });
  };

  const pendingWaivers = waivers.filter(w => w.status === 'pending');
  const pastWaivers = waivers.filter(w => w.status !== 'pending');

  // ── Pin the highlighted student's waiver at the top ──
  const sortedPending = highlightStudentName
    ? [
        ...pendingWaivers.filter(w =>
          w.student_name?.toLowerCase().includes(highlightStudentName.toLowerCase())
        ),
        ...pendingWaivers.filter(w =>
          !w.student_name?.toLowerCase().includes(highlightStudentName.toLowerCase())
        ),
      ]
    : pendingWaivers;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Fee Waiver & Bursary Approvals" maxWidth="2xl">
      <div className="space-y-6">
        {/* Context banner when opened from a specific student row */}
        {highlightStudentName && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center gap-3 text-xs">
            <ShieldCheck className="w-4 h-4 text-amber-400 shrink-0" />
            <span className="text-amber-300">
              Viewing waiver requests for <strong className="text-white">{highlightStudentName}</strong>.
              Their pending request is shown first.
            </span>
          </div>
        )}

        {actionSuccess && (
          <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 flex items-center gap-2.5 font-medium shadow-sm">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
        )}

        {actionError && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-400 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {/* ── Pending Waivers Section ── */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-400" />
              Pending Requests ({pendingWaivers.length})
            </h3>
            <span className="text-[10px] text-slate-400">
              {isDirector ? 'Director Authorization Required' : 'Submitted to Director for Review'}
            </span>
          </div>

          {isLoading ? (
            <p className="text-xs text-slate-400 py-4 text-center">Loading waiver requests...</p>
          ) : sortedPending.length === 0 ? (
            <div className="p-6 bg-slate-800/40 rounded-xl border border-slate-700/50 text-center">
              <ShieldCheck className="w-8 h-8 text-emerald-400 mx-auto mb-2 opacity-60" />
              <p className="text-xs text-slate-300 font-medium">All caught up!</p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {highlightStudentName
                  ? `No pending waiver for ${highlightStudentName}. The Bursar may not have submitted one yet.`
                  : 'No fee waivers are currently pending approval.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {sortedPending.map((w) => {
                const isHighlighted = highlightStudentName
                  ? w.student_name?.toLowerCase().includes(highlightStudentName.toLowerCase())
                  : false;
                return (
                  <div
                    key={w.id}
                    className={`p-4 rounded-xl space-y-3 border ${
                      isHighlighted
                        ? 'bg-amber-500/5 border-amber-500/40 ring-1 ring-amber-500/20'
                        : 'bg-slate-800/80 border-slate-700/80'
                    }`}
                  >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <span className="text-xs font-bold text-white">{w.student_name || 'Student'}</span>
                      <span className="text-[10px] font-mono text-emerald-400 ml-2">{w.student_id_code}</span>
                      <p className="text-xs text-slate-400 mt-0.5">
                        <strong className="text-amber-300 font-mono">UGX {Number(w.amount).toLocaleString()}</strong> — {w.reason}
                      </p>
                      {w.requested_by_name && (
                        <p className="text-[10px] text-slate-500 mt-1 flex items-center gap-1">
                          <User className="w-3 h-3" /> Requested by {w.requested_by_name}
                        </p>
                      )}
                    </div>
                    <Badge variant="warning" size="sm">Pending Approval</Badge>
                  </div>

                  {/* Reject reason input prompt */}
                  {rejectingId === w.id ? (
                    <div className="p-3 bg-slate-900 border border-rose-500/30 rounded-lg space-y-2">
                      <p className="text-xs text-rose-300 font-semibold">Provide rejection reason:</p>
                      <input
                        type="text"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="e.g. Ineligible under current term policy..."
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                        autoFocus
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[11px]"
                          onClick={() => setRejectingId(null)}
                        >
                          Cancel
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          className="text-[11px]"
                          disabled={isRejecting}
                          onClick={() => handleConfirmReject(w.id)}
                        >
                          Confirm Rejection
                        </Button>
                      </div>
                    </div>
                  ) : (
                    isDirector ? (() => {
                      const currentUserName = `${user?.first_name || ''} ${user?.last_name || ''}`.trim().toLowerCase();
                      const isBursarSelfRequested = !!(
                        user?.role === 'bursar' &&
                        currentUserName &&
                        w.requested_by_name &&
                        w.requested_by_name.trim().toLowerCase() === currentUserName
                      );

                      return (
                        <div className="pt-2 border-t border-slate-700/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                          {isBursarSelfRequested ? (
                            <p className="text-[11px] text-amber-400/90 font-medium">
                              Segregation of duties: You cannot approve your own waiver request.
                            </p>
                          ) : (
                            <span />
                          )}
                          <div className="flex justify-end gap-2 w-full sm:w-auto">
                            <Button
                              variant="ghost"
                              size="sm"
                              leftIcon={<X className="w-3.5 h-3.5 text-rose-400" />}
                              className="text-xs text-rose-400 hover:text-rose-300"
                              onClick={() => handleStartReject(w.id)}
                              disabled={isApproving || isRejecting}
                            >
                              Reject
                            </Button>
                            <Button
                              variant="primary"
                              size="sm"
                              leftIcon={<Check className="w-3.5 h-3.5" />}
                              className={`text-xs ${isBursarSelfRequested ? 'opacity-50 cursor-not-allowed bg-slate-700' : 'bg-emerald-600 hover:bg-emerald-500'}`}
                              onClick={() => !isBursarSelfRequested && approveWaiver(w.id)}
                              disabled={isApproving || isRejecting || isBursarSelfRequested}
                              title={isBursarSelfRequested ? 'Segregation of duties: Cannot approve your own request' : 'Approve waiver'}
                            >
                              Approve Waiver
                            </Button>
                          </div>
                        </div>
                      );
                    })() : (
                      /* Bursar read-only notice — approval is exclusively for the Director */
                      <div className="pt-2 border-t border-slate-700/50">
                        <p className="text-[11px] text-slate-400 flex items-center gap-1.5 italic">
                          <ShieldCheck className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                          Awaiting Director authorization — approval actions are restricted to the Director.
                        </p>
                      </div>
                    )
                  )}
                 </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Past Decision History ───────────────────────────────────────── */}
        {pastWaivers.length > 0 && (
          <div>
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
              Recent Decisions
            </h4>
            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {pastWaivers.slice(0, 10).map((w) => (
                <div
                  key={w.id}
                  className="p-2.5 bg-slate-900/60 border border-slate-800 rounded-lg flex items-center justify-between text-xs"
                >
                  <div>
                    <span className="font-semibold text-slate-200">{w.student_name}</span>
                    <span className="text-slate-400 font-mono ml-2">UGX {Number(w.amount).toLocaleString()}</span>
                    <p className="text-[10px] text-slate-500">{w.reason}</p>
                    {w.rejection_reason && (
                      <p className="text-[10px] text-rose-400 font-medium mt-0.5">
                        Reason: {w.rejection_reason}
                      </p>
                    )}
                  </div>
                  <Badge
                    variant={w.status === 'approved' ? 'success' : 'danger'}
                    size="sm"
                  >
                    {w.status === 'approved' ? 'Approved' : 'Rejected'}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
