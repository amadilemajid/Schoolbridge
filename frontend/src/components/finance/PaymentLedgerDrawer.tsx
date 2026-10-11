import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Drawer } from '../ui/Drawer';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { useRbac } from '../../hooks/useRbac';
import { useAuth } from '../../context/AuthContext';
import { RotateCcw, AlertTriangle, Printer, Clock, CheckCircle2, ShieldAlert, ShieldCheck, User, UserCheck, Calendar } from 'lucide-react';

interface Payment {
  id: string;
  amount: number | string;
  method: string;
  status: string;
  payment_date: string;
  is_reversed: boolean;
  receipt_number: string;
  notes?: string;
  payer_name?: string;
  bank_reference?: string;
  recorded_by?: any;
  recorded_by_name?: string;
  requires_approval?: boolean;
}

interface ExistingInstalment {
  id: string;
  instalment_number: number;
  amount_due?: number;
  amount?: number;
  amount_paid?: number;
  due_date: string;
  status: 'pending' | 'partial' | 'paid' | 'overdue' | 'waived';
}

interface ExistingPlan {
  id: string;
  total_amount: number;
  status: 'active' | 'completed' | 'defaulted' | 'cancelled';
  instalments: ExistingInstalment[];
  created_at: string;
}

// ── Inline approve button used inside ledger rows ──
const ApprovePaymentButton: React.FC<{ paymentId: string; onApproved: () => void }> = ({ paymentId, onApproved }) => {
  const { mutate, isPending, isSuccess } = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/payments/payments/${paymentId}/approve/`);
      return res.data;
    },
    onSuccess: () => {
      onApproved();
    },
  });

  if (isSuccess) {
    return (
      <span className="text-[11px] text-emerald-400 font-bold flex items-center gap-1">
        <CheckCircle2 className="w-3.5 h-3.5" /> Approved
      </span>
    );
  }

  return (
    <Button
      variant="primary"
      size="sm"
      isLoading={isPending}
      leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
      className="text-[11px] bg-emerald-600 hover:bg-emerald-500 text-white shrink-0"
      onClick={() => mutate()}
    >
      Approve
    </Button>
  );
};

interface PaymentLedgerDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  feeRecordId?: string;
  studentId: string;
  studentCode?: string;
  studentName: string;
  className?: string;
  totalAmount?: number;
  amountPaid?: number;
  amountWaived?: number;
  balance?: number;
  hasPaymentPlan?: boolean;
  onPaymentReversed?: (studentId: string, reversedAmount: number) => void;
}

export const PaymentLedgerDrawer: React.FC<PaymentLedgerDrawerProps> = ({
  isOpen,
  onClose,
  feeRecordId,
  studentId,
  studentCode,
  studentName,
  className = '',
  totalAmount = 0,
  amountPaid = 0,
  amountWaived = 0,
  balance = 0,
  hasPaymentPlan = false,
  onPaymentReversed,
}) => {
  const { isDirector } = useRbac();
  const { tenant, user } = useAuth();
  const queryClient = useQueryClient();
  const schoolName = tenant?.name || 'SchoolBridge Portal';

  const [reversingPaymentId, setReversingPaymentId] = useState<string | null>(null);
  const [reversalReason, setReversalReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const [localReversedIds, setLocalReversedIds] = useState<Set<string>>(new Set());
  const [reversalSuccessId, setReversalSuccessId] = useState<string | null>(null);

  const displayStudentCode = studentCode || studentId;

  // Reset local state when drawer opens for a new student
  useEffect(() => {
    if (isOpen) {
      setLocalReversedIds(new Set());
      setReversalSuccessId(null);
      setReversingPaymentId(null);
      setReversalReason('');
      setError(null);
    }
  }, [isOpen, studentId]);

  // Fetch payments for this student
  const { data: paymentsData, isLoading, refetch } = useQuery({
    queryKey: ['student-payments', studentId, feeRecordId],
    queryFn: async () => {
      const param = feeRecordId ? { fee_record: feeRecordId } : { student: studentId };
      const res = await apiClient.get('/payments/payments/', { params: param });
      const raw = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      return raw.filter((p: any) => {
        if (feeRecordId && p.fee_record) {
          const pFid = typeof p.fee_record === 'object' ? p.fee_record.id : p.fee_record;
          return String(pFid) === String(feeRecordId);
        }
        const pSid = typeof p.student === 'object' ? p.student.id : p.student;
        return String(pSid) === String(studentId);
      });
    },
    enabled: isOpen && (!!studentId || !!feeRecordId),
  });

  // Fetch active payment plan if present
  const { data: planData } = useQuery<ExistingPlan | null>({
    queryKey: ['payment-plan', feeRecordId],
    queryFn: async () => {
      if (!feeRecordId) return null;
      const res = await apiClient.get('/payments/payment-plans/', {
        params: { fee_record: feeRecordId },
      });
      const results = res.data?.results || res.data || [];
      return results[0] || null;
    },
    enabled: isOpen && (hasPaymentPlan || !!feeRecordId),
  });

  const payments: Payment[] = paymentsData || [];

  const { mutate: reversePayment, isPending } = useMutation({
    mutationFn: async ({ paymentId, reason }: { paymentId: string; reason: string }) => {
      const res = await apiClient.post(`/payments/payments/${paymentId}/reverse/`, { reason });
      return { paymentId, data: res.data };
    },
    onSuccess: ({ paymentId }) => {
      refetch();
      const targetPayment = payments.find((p: Payment) => p.id === paymentId);

      setLocalReversedIds(prev => new Set([...prev, paymentId]));
      setReversalSuccessId(paymentId);

      if (onPaymentReversed && targetPayment) {
        onPaymentReversed(studentId, Number(targetPayment.amount));
      }

      setReversingPaymentId(null);
      setReversalReason('');
      setError(null);
    },
    onError: (err: any) => {
      const raw = err.response?.data;
      const msg: string =
        (typeof raw?.error === 'string' ? raw.error : null) ||
        (typeof raw?.detail === 'string' ? raw.detail : null) ||
        (typeof raw?.reason === 'string' ? raw.reason : null) ||
        'Failed to reverse payment. Only Directors can reverse payments.';
      setError(msg);
    },
  });

  const handleReverseSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!reversingPaymentId) return;
    if (reversalReason.trim().length < 10) {
      setError('A valid reason (minimum 10 characters) is required for reversal.');
      return;
    }
    reversePayment({ paymentId: reversingPaymentId, reason: reversalReason });
  };

  const getPayerName = (payment: Payment): string => {
    if (payment.payer_name && payment.payer_name.trim()) return payment.payer_name.trim();
    if (payment.notes) {
      if (payment.notes.toLowerCase().includes('payer:')) {
        const match = payment.notes.match(/payer:\s*([^|\n]+)/i);
        if (match && match[1]) return match[1].trim();
      }
      return payment.notes.trim();
    }
    return '';
  };

  const getRecordedByName = (payment: Payment): string => {
    if (payment.recorded_by_name) return payment.recorded_by_name;
    if (typeof payment.recorded_by === 'object' && payment.recorded_by) {
      const first = payment.recorded_by.first_name || '';
      const last = payment.recorded_by.last_name || '';
      const full = `${first} ${last}`.trim();
      if (full) return full;
      if (payment.recorded_by.username) return payment.recorded_by.username;
    }
    if (user?.first_name || user?.last_name) {
      return `${user.first_name || ''} ${user.last_name || ''}`.trim();
    }
    return 'Bursar Office';
  };

  const handleReprint = (payment: Payment) => {
    const amountNum = Number(payment.amount) || 0;
    const cashier = getRecordedByName(payment);
    const payer = getPayerName(payment);
    const cleanNotes = payment.notes ? payment.notes.replace(/Payer:\s*[^|\n]+(\s*\|\s*)?/i, '').trim() : '';
    const printDate = new Date(payment.payment_date).toLocaleDateString('en-UG', {
      weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
    });
    const printTime = new Date(payment.payment_date).toLocaleTimeString('en-UG', {
      hour: '2-digit', minute: '2-digit',
    });

    const methodLabels: Record<string, string> = {
      cash: 'Cash Payment',
      bank: 'Bank Direct Deposit',
      momo: 'Mobile Money',
      mtn_momo: 'MTN MoMo',
      airtel_money: 'Airtel Money',
    };
    const cleanMethod = methodLabels[payment.method.toLowerCase()] || payment.method.toUpperCase();

    const sortedPayments = [...payments]
      .filter((p: Payment) => !p.is_reversed && p.status === 'completed')
      .sort((a: Payment, b: Payment) => new Date(a.payment_date).getTime() - new Date(b.payment_date).getTime());

    let runningPaid = 0;
    let paymentIndex = sortedPayments.findIndex((p: Payment) => p.id === payment.id);

    if (paymentIndex !== -1) {
      for (let i = 0; i <= paymentIndex; i++) {
        runningPaid += Number(sortedPayments[i].amount) || 0;
      }
    } else {
      runningPaid = amountPaid;
    }

    const prevBalanceAtPayment = totalAmount - (runningPaid - amountNum);
    const remainingBalanceAtPayment = totalAmount - runningPaid;

    const printContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Receipt — ${payment.receipt_number}</title>
        <style>
          * { margin: 0; padding: 0; box-sizing: border-box; }
          body { font-family: 'Courier New', Courier, monospace; font-size: 13px; width: 80mm; margin: 0 auto; padding: 12px; color: #111; }
          .header { text-align: center; border-bottom: 2px dashed #000; padding-bottom: 8px; margin-bottom: 8px; }
          .school-title { font-size: 15px; font-weight: bold; text-transform: uppercase; }
          .sub { font-size: 11px; margin-top: 2px; }
          .receipt-title { font-size: 13px; font-weight: bold; margin-top: 6px; letter-spacing: 1px; }
          .row { display: flex; justify-content: space-between; margin: 4px 0; font-size: 12px; }
          .divider { border-top: 1px dashed #000; margin: 8px 0; }
          .total-box { border-top: 2px solid #000; border-bottom: 2px solid #000; padding: 6px 0; margin: 8px 0; font-size: 13px; font-weight: bold; }
          .amount-highlight { font-size: 15px; font-weight: bold; color: #000; }
          .footer { text-align: center; font-size: 10px; margin-top: 12px; color: #555; }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="school-title">${schoolName}</div>
          <div class="sub">Uganda &bull; Official Fee Receipt</div>
          <div class="receipt-title">RECEIPT: ${payment.receipt_number || 'REC-CSH'}</div>
        </div>
        <div class="row"><span>Date:</span><span>${printDate} ${printTime}</span></div>
        <div class="row"><span>Student:</span><span>${studentName}</span></div>
        <div class="row"><span>Student Code:</span><span>${displayStudentCode}</span></div>
        ${payer ? `<div class="row"><span>Payer / Depositor:</span><span style="font-weight: bold;">${payer}</span></div>` : ''}
        ${cleanNotes ? `<div class="row"><span>Notes / Remarks:</span><span>${cleanNotes}</span></div>` : ''}
        <div class="row"><span>Class:</span><span>${className}</span></div>
        <div class="divider"></div>
        <div class="row"><span>Previous Balance:</span><span>UGX ${prevBalanceAtPayment.toLocaleString()}</span></div>
        <div class="total-box row">
          <span>AMOUNT PAID:</span>
          <span class="amount-highlight">UGX ${amountNum.toLocaleString()}</span>
        </div>
        <div class="row"><span>Remaining Balance:</span><span>UGX ${remainingBalanceAtPayment.toLocaleString()}</span></div>
        <div class="divider"></div>
        <div class="row"><span>Payment Method:</span><span>${cleanMethod}</span></div>
        <div class="row"><span>Status:</span><span>${payment.status.toUpperCase()}</span></div>
        <div class="divider"></div>
        <div class="row"><span>Cashier / Bursar:</span><span>${cashier}</span></div>
        <div class="footer">
          <p>Thank you for your payment.</p>
          <p>Retain this receipt for audit purposes.</p>
          <p>SchoolBridge ERP &bull; Verified</p>
        </div>
      </body>
      </html>
    `;

    const printWindow = window.open('', '_blank', 'width=450,height=650');
    if (printWindow) {
      printWindow.document.write(printContent);
      printWindow.document.close();
      printWindow.focus();
      setTimeout(() => {
        printWindow.print();
      }, 300);
    }
  };

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Payment Ledger & History">
      <div className="space-y-6">

        {/* Student Summary Header Card */}
        <div className="p-4 bg-slate-800 rounded-xl border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Student Account</p>
              <h2 className="text-lg font-bold text-white tracking-tight">{studentName}</h2>
              <p className="text-xs font-mono font-semibold text-emerald-400">
                {displayStudentCode} &bull; <span className="text-slate-400 font-sans">{className}</span>
              </p>
            </div>
            <div className="text-right">
              <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                balance <= 0 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
              }`}>
                {balance <= 0 ? '✓ CLEARED' : `BAL: UGX ${balance.toLocaleString()}`}
              </span>
            </div>
          </div>

          <div className={`grid gap-2 pt-3 border-t border-slate-700/60 mt-3 text-center ${
            amountWaived > 0 ? 'grid-cols-4' : 'grid-cols-3'
          }`}>
            <div className="bg-slate-900/50 p-2 rounded-lg">
              <p className="text-[10px] text-slate-400 uppercase">Total Fees</p>
              <p className="text-xs font-bold text-white">UGX {totalAmount.toLocaleString()}</p>
            </div>
            <div className="bg-slate-900/50 p-2 rounded-lg">
              <p className="text-[10px] text-slate-400 uppercase">Paid to Date</p>
              <p className="text-xs font-bold text-emerald-400">UGX {amountPaid.toLocaleString()}</p>
            </div>
            {amountWaived > 0 && (
              <div className="bg-indigo-950/30 border border-indigo-500/20 p-2 rounded-lg">
                <p className="text-[10px] text-indigo-300 uppercase">Waived</p>
                <p className="text-xs font-bold text-indigo-400">UGX {amountWaived.toLocaleString()}</p>
              </div>
            )}
            <div className="bg-slate-900/50 p-2 rounded-lg">
              <p className="text-[10px] text-slate-400 uppercase">Balance</p>
              <p className="text-xs font-bold text-amber-400">UGX {balance.toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* Active Payment Plan Schedule Card (if plan exists) */}
        {planData && planData.instalments && planData.instalments.length > 0 && (
          <div className="p-4 bg-slate-800/80 rounded-xl border border-indigo-500/30 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-indigo-500/20 text-indigo-400 rounded-lg">
                  <Calendar className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-white">Active Payment Plan</h3>
                  <p className="text-[10px] text-slate-400">
                    {planData.instalments.length}-instalment agreement &bull; Total: UGX {Number(planData.total_amount).toLocaleString()}
                  </p>
                </div>
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                planData.status === 'completed'
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
                  : 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30'
              }`}>
                {planData.status}
              </span>
            </div>

            <div className="divide-y divide-slate-700/60 bg-slate-900/60 rounded-lg overflow-hidden border border-slate-700/60">
              {planData.instalments.map((inst, idx) => {
                const dueAmt = Number(inst.amount_due ?? inst.amount ?? 0);
                const paidAmt = Number(inst.amount_paid ?? 0);
                const statusStyles: Record<string, string> = {
                  pending: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
                  partial: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
                  paid: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
                  overdue: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
                  waived: 'text-slate-400 bg-slate-500/10 border-slate-500/30',
                };

                return (
                  <div key={inst.id || idx} className="p-2.5 flex items-center justify-between text-xs gap-3">
                    <div>
                      <p className="font-semibold text-slate-200">
                        Instalment #{inst.instalment_number}
                      </p>
                      <p className="text-[10px] text-slate-400 flex items-center gap-1">
                        <Clock className="w-3 h-3 text-slate-500" />
                        Due {inst.due_date ? new Date(inst.due_date).toLocaleDateString('en-UG', { day: '2-digit', month: 'short', year: 'numeric' }) : 'N/A'}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 text-right">
                      <div>
                        <p className="font-bold text-white">UGX {dueAmt.toLocaleString()}</p>
                        {paidAmt > 0 && (
                          <p className="text-[9px] text-emerald-400 font-medium">Paid: UGX {paidAmt.toLocaleString()}</p>
                        )}
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase border ${statusStyles[inst.status] || 'text-slate-400'}`}>
                        {inst.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl flex gap-3 text-rose-400 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <p>{error}</p>
          </div>
        )}

        {/* Transaction History Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200">Transaction Entries ({payments.length})</h3>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Oldest First</span>
          </div>

          {isLoading ? (
            <div className="text-center py-8 text-slate-400 text-sm animate-pulse">Loading ledger...</div>
          ) : payments.length === 0 ? (
            <div className="text-center py-8 text-slate-500 text-sm bg-slate-800/50 rounded-xl border border-slate-800 border-dashed">
              No payments recorded yet.
            </div>
          ) : (() => {
            // ── Issue 1 Fix: True chronological order (oldest → newest) ──
            const chronologicalPayments = [...payments].sort(
              (a: Payment, b: Payment) => new Date(a.payment_date).getTime() - new Date(b.payment_date).getTime()
            );

            // ── Issue 2 Fix: Compute running balance per transaction ──
            const METHOD_LABELS: Record<string, string> = {
              cash: 'Cash Payment',
              bank: 'Bank Direct Deposit',
              momo: 'Mobile Money',
              mtn_momo: 'MTN MoMo',
              airtel_money: 'Airtel Money',
            };

            let runningBalance = totalAmount;
            const enriched = chronologicalPayments.map((payment: Payment) => {
              const amountNum = Number(payment.amount) || 0;
              const isActive = !(payment.is_reversed || localReversedIds.has(payment.id)) && payment.status === 'completed';
              const prevBal = runningBalance;
              if (isActive) runningBalance = runningBalance - amountNum;
              return { payment, amountNum, prevBal, balanceAfter: runningBalance };
            });

            return enriched.map(({ payment, amountNum, prevBal, balanceAfter }) => {
              const isReversed = payment.is_reversed || localReversedIds.has(payment.id);
              const justReversed = reversalSuccessId === payment.id;
              const cashierName = getRecordedByName(payment);

              // ── Issue 3 Fix: Clean method label ──
              const cleanMethod = METHOD_LABELS[payment.method.toLowerCase()] || payment.method.replace(/_/g, ' ');

              // ── Issue 5 Fix: Never show literal 'REC-CSH' fallback ──
              const displayRef = payment.receipt_number?.trim()
                ? payment.receipt_number
                : `AUTO-${payment.id.slice(0, 8).toUpperCase()}`;

              return (
                <div
                  key={payment.id}
                  className={`p-4 rounded-xl border transition-all duration-300 ${
                    isReversed
                      ? 'bg-rose-950/20 border-rose-900/40'
                      : 'bg-slate-800/60 border-slate-700/70 hover:border-slate-600'
                  }`}
                >
                  {/* Just-reversed notification */}
                  {justReversed && (
                    <div className="mb-3 p-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-center gap-2 text-xs text-emerald-400 font-semibold">
                      <CheckCircle2 className="w-4 h-4 shrink-0" />
                      Reversal authorized. Balance restored immediately.
                    </div>
                  )}

                  {/* Amount + Status Row */}
                  <div className="flex justify-between items-start mb-2.5">
                    <div>
                      <p className={`text-lg font-bold tracking-tight ${isReversed ? 'text-rose-400 line-through' : 'text-emerald-400'}`}>
                        UGX {amountNum.toLocaleString()}
                      </p>
                      <p className="text-xs text-slate-400 flex items-center gap-1.5 mt-1">
                        <Clock className="w-3.5 h-3.5 text-slate-500" />
                        {new Date(payment.payment_date).toLocaleString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric',
                          hour: 'numeric', minute: '2-digit',
                        })}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        isReversed
                          ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                          : payment.status === 'pending'
                          ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                          : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                      }`}>
                        {isReversed ? '⊘ Reversed' : payment.status === 'pending' ? '⏳ Pending Approval' : payment.status}
                      </span>
                      {/* ── Issue 3 Fix: Human-readable method ── */}
                      <p className="text-[10px] text-slate-400 mt-1 font-semibold">{cleanMethod}</p>
                    </div>
                  </div>

                  {/* ── Pending Approval Warning Banner ── */}
                  {!isReversed && payment.status === 'pending' && (
                    <div className="flex items-start gap-2.5 p-3 bg-amber-950/40 border border-amber-500/40 rounded-xl mb-2">
                      <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="text-xs font-bold text-amber-300">
                          Awaiting Director Approval
                        </p>
                        <p className="text-[11px] text-amber-300/70 mt-0.5">
                          This payment of <strong>UGX {amountNum.toLocaleString()}</strong> exceeds the UGX 500,000 threshold and has not been applied to the balance yet.
                        </p>
                      </div>
                      {isDirector && (
                        <ApprovePaymentButton paymentId={payment.id} onApproved={() => {
                          refetch();
                          if (onPaymentReversed) onPaymentReversed(studentId, 0); // trigger parent refresh
                          queryClient.invalidateQueries({ queryKey: ['fee-records'] });
                          queryClient.invalidateQueries({ queryKey: ['pending-payments-queue'] });
                        }} />
                      )}
                    </div>
                  )}

                  {/* ── Issue 2 Fix: Running balance row ── */}
                  {!isReversed && payment.status === 'completed' && (
                    <div className="flex justify-between items-center text-[11px] mb-2 bg-slate-900/50 rounded-lg px-3 py-2">
                      <span className="text-slate-500">Balance before:</span>
                      <span className="font-mono text-slate-300 font-medium">UGX {prevBal.toLocaleString()}</span>
                      <span className="text-slate-600 mx-1">→</span>
                      <span className="text-slate-500">After payment:</span>
                      <span className={`font-mono font-bold ${balanceAfter <= 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                        UGX {Math.max(0, balanceAfter).toLocaleString()}
                      </span>
                    </div>
                  )}

                  {/* Payer / Guardian Depositor */}
                  {getPayerName(payment) ? (
                    <div className="flex items-center gap-2 text-xs text-slate-300 mb-2.5 bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-3 py-2">
                      <UserCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span className="text-slate-400">Payer / Depositor:</span>
                      <span className="font-semibold text-emerald-300">{getPayerName(payment)}</span>
                    </div>
                  ) : null}

                  {/* Payment Notes / Remarks */}
                  {payment.notes && (() => {
                    const clean = payment.notes.replace(/Payer:\s*[^|\n]+(\s*\|\s*)?/i, '').trim();
                    if (!clean) return null;
                    return (
                      <div className="text-[11px] text-slate-300 mb-2.5 bg-slate-800/80 border border-slate-700/60 rounded-lg px-3 py-2 flex items-start gap-2">
                        <span className="text-slate-400 font-semibold uppercase tracking-wider text-[9px] mt-0.5">Notes:</span>
                        <span className="text-slate-200">{clean}</span>
                      </div>
                    );
                  })()}

                  {/* Reference & Attributed Cashier */}
                  <div className="flex justify-between items-center text-xs text-slate-400 border-t border-slate-700/50 pt-2.5">
                    <p>Ref: <span className="font-mono text-slate-200 font-medium">{displayRef}</span></p>
                    <p className="flex items-center gap-1" title="Staff member who recorded and verified this payment">
                      <User className="w-3 h-3 text-slate-500" />
                      <span>Cashier:</span>
                      <span className="text-slate-200 font-medium">{cashierName}</span>
                    </p>
                  </div>

                  {/* Action Buttons */}
                  {/* ── Issue 4 Fix: Button text includes ref+amount so context survives scroll ── */}
                  {!isReversed && payment.status === 'completed' && (
                    <div className="mt-3.5 pt-3 border-t border-slate-700/50 flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        leftIcon={<Printer className="w-3.5 h-3.5" />}
                        className="flex-1 text-xs"
                        onClick={() => handleReprint(payment)}
                        title={`Reprint receipt ${displayRef} — UGX ${amountNum.toLocaleString()}`}
                      >
                        Reprint Receipt ({displayRef})
                      </Button>

                      {/* Reversal action strictly controlled by Director role */}
                      {isDirector ? (
                        <Button
                          variant="danger"
                          size="sm"
                          leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
                          className="text-xs"
                          onClick={() => {
                            setReversingPaymentId(payment.id);
                            setReversalSuccessId(null);
                            setError(null);
                          }}
                        >
                          Reverse
                        </Button>
                      ) : (
                        <span className="text-[10px] text-slate-500 italic flex items-center gap-1" title="Only Directors can authorize reversals">
                          <ShieldCheck className="w-3 h-3 text-slate-500" />
                          Director Only
                        </span>
                      )}
                    </div>
                  )}

                  {/* Reversed note */}
                  {isReversed && !justReversed && (
                    <div className="mt-2.5 pt-2 border-t border-rose-900/30">
                      <p className="text-[11px] text-rose-400/80 italic">This payment has been reversed and excluded from balance.</p>
                    </div>
                  )}

                  {/* Director Inline Reversal Form */}
                  {reversingPaymentId === payment.id && !isReversed && isDirector && (
                    <form
                      onSubmit={handleReverseSubmit}
                      className="mt-3.5 p-3.5 bg-slate-900 rounded-xl border border-rose-500/40 space-y-3"
                    >
                      <p className="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5" /> Authorize Reversal (Director Action)
                      </p>
                      <TextInput
                        label="Reason for Reversal (Required — min 10 characters)"
                        placeholder="e.g. Bank correction — deposit reversed by sender bank"
                        value={reversalReason}
                        onChange={(e) => setReversalReason(e.target.value)}
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          type="button"
                          onClick={() => {
                            setReversingPaymentId(null);
                            setReversalReason('');
                            setError(null);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          type="submit"
                          isLoading={isPending}
                        >
                          Confirm Reversal
                        </Button>
                      </div>
                    </form>
                  )}
                </div>
              );
            });
          })()}
        </div>
      </div>
    </Drawer>
  );
};

