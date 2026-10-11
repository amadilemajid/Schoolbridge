import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { DataTable } from '../../components/ui/DataTable';
import type { Column } from '../../components/ui/DataTable';
import { TablePagination } from '../../components/ui/TablePagination';
import { FilterBar } from '../../components/ui/FilterBar';
import { Badge } from '../../components/ui/Badge';
import type { BadgeVariant } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { StatGroup } from '../../components/dashboard/StatGroup';
import { KpiCard } from '../../components/dashboard/KpiCard';
import { RecordPaymentModal } from '../../components/finance/RecordPaymentModal';
import { PaymentPlanModal } from '../../components/finance/PaymentPlanModal';
import { PaymentLinkModal } from '../../components/finance/PaymentLinkModal';
import { PaymentLedgerDrawer } from '../../components/finance/PaymentLedgerDrawer';
import { BulkReminderModal } from '../../components/finance/BulkReminderModal';
import { EndOfDayModal } from '../../components/finance/EndOfDayModal';
import { ApplyWaiverModal } from '../../components/finance/ApplyWaiverModal';
import { PendingWaiversBadge } from '../../components/finance/PendingWaiversBadge';
import { PendingPaymentsBadge } from '../../components/finance/PendingPaymentsBadge';
import { ReviewWaiversModal } from '../../components/finance/ReviewWaiversModal';
import { FeeStructuresTab } from '../../components/finance/FeeStructuresTab';
import { ApprovalQueueBanner } from '../../components/finance/ApprovalQueueBanner';
import {
  CreditCard,
  Banknote,
  AlertTriangle,
  Calendar,
  Link2,
  ArrowRight,
  CheckCircle2,
  Eye,
  Megaphone,
  Layers,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useEffect } from 'react';
import { RbacGate } from '../../components/auth/RbacGate';
import { useRbac } from '../../hooks/useRbac';

// ─── Types ────────────────────────────────────────────────────────────────────
interface FeeRecord {
  id: string;
  student: string | {
    id: string;
    student_id: string;
    first_name: string;
    last_name: string;
    current_class?: { name: string };
  };
  student_name?: string;
  student_id_code?: string;
  class_name?: string;
  total_amount: number;
  amount_paid: number;
  amount_waived: number;
  balance: number;
  is_fully_paid: boolean;
  escalation_level?: number;
  has_payment_plan?: boolean;
  payment_plan_installments?: number;
  has_pending_waiver?: boolean;
  pending_waiver_amount?: number;
  pending_waiver_id?: string;
  pending_waiver_reason?: string;
  has_pending_payment?: boolean;
  pending_payment_amount?: number;
  pending_payment_id?: string;
  last_payment_date?: string;
  clearance_date?: string;
}

const getStudentName = (rec: FeeRecord): string => {
  if (rec.student_name) return rec.student_name;
  if (typeof rec.student === 'object' && rec.student) {
    return `${rec.student.first_name || ''} ${rec.student.last_name || ''}`.trim() || 'Unknown Student';
  }
  return 'Unknown Student';
};

const getStudentCode = (rec: FeeRecord): string => {
  if (rec.student_id_code) return rec.student_id_code;
  if (typeof rec.student === 'object' && rec.student) {
    return rec.student.student_id || '';
  }
  return '';
};

const getStudentId = (rec: FeeRecord): string => {
  if (typeof rec.student === 'string') return rec.student;
  if (typeof rec.student === 'object' && rec.student) return rec.student.id;
  return rec.id;
};

const getClassName = (rec: FeeRecord): string => {
  if (rec.class_name) return rec.class_name;
  if (typeof rec.student === 'object' && rec.student?.current_class) {
    return rec.student.current_class.name || 'Unassigned';
  }
  return 'Unassigned';
};

const getNum = (v: any): number => {
  const n = typeof v === 'number' ? v : parseFloat(v);
  return isNaN(n) ? 0 : n;
};


// ─── Status helpers ───────────────────────────────────────────────────────────
type PayStatus = 'cleared' | 'pending_approval' | 'partial_plan' | 'partial' | 'unpaid' | 'defaulter';

function getStatus(rec: FeeRecord): PayStatus {
  const balance = getNum(rec.balance);
  const paid = getNum(rec.amount_paid);
  const escalation = getNum(rec.escalation_level);

  if (rec.has_pending_waiver || rec.has_pending_payment) return 'pending_approval';
  if (balance <= 0 || rec.is_fully_paid) return 'cleared';
  if (rec.has_payment_plan) return 'partial_plan';
  if (escalation >= 3) return 'defaulter';
  if (paid > 0) return 'partial';
  return 'unpaid';
}

const STATUS_CONFIG: Record<PayStatus, { label: string; variant: BadgeVariant; description: string }> = {
  cleared:          { label: 'Cleared',          variant: 'success', description: 'Fully paid — no balance outstanding' },
  pending_approval: { label: 'Pending Approval', variant: 'warning', description: 'Fee waiver / bursary requested — awaiting Director authorization' },
  partial_plan:     { label: 'Partial',          variant: 'warning', description: 'Partial payment — active instalment plan' },
  partial:          { label: 'Partial',          variant: 'warning', description: 'Partial payment — no plan yet' },
  unpaid:           { label: 'Unpaid',           variant: 'neutral', description: 'No payment received this term' },
  defaulter:        { label: 'Defaulter',        variant: 'danger',  description: 'Escalated — parent contact required' },
};

const fmt = (n: number) => `UGX ${n.toLocaleString()}`;

// ─── Component ────────────────────────────────────────────────────────────────
export const FeeManagementPage: React.FC = () => {
  const { isDirector } = useRbac();
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [classFilter, setClassFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const [searchParams] = useSearchParams();

  const queryClient = useQueryClient();

  const [mainTab, setMainTab] = useState<'accounts' | 'structures'>('accounts');
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [ledgerModalOpen, setLedgerModalOpen] = useState(false);
  const [bulkReminderOpen, setBulkReminderOpen] = useState(false);
  const [endOfDayOpen, setEndOfDayOpen] = useState(false);
  const [waiverModalOpen, setWaiverModalOpen] = useState(false);
  const [reviewWaiversOpen, setReviewWaiversOpen] = useState(false);
  const [selectedFeeRecord, setSelectedFeeRecord] = useState<FeeRecord | null>(null);
  const [toast, setToast] = useState<{ show: boolean; title: string; message: string; type?: 'success' | 'info' | 'warning' } | null>(null);

  const showToast = (title: string, message: string, type: 'success' | 'info' | 'warning' = 'success') => {
    setToast({ show: true, title, message, type });
    setTimeout(() => setToast(null), 6000);
  };

  // Sync sub-navigation query parameters
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam === 'structures') {
      setMainTab('structures');
    } else if (tabParam === 'accounts') {
      setMainTab('accounts');
    }

    const filterParam = searchParams.get('filter');
    const actionParam = searchParams.get('action');

    if (filterParam === 'defaulter') {
      setStatusFilter('defaulter');
    } else if (filterParam === 'plan') {
      setStatusFilter('partial_plan');
    } else if (filterParam === 'cleared') {
      setStatusFilter('cleared');
    }

    if (actionParam === 'waivers' || actionParam === 'waiver_approvals') {
      setReviewWaiversOpen(true);
    } else if (actionParam === 'waiver_request') {
      setWaiverModalOpen(true);
    } else if (actionParam === 'record_payment') {
      setRecordModalOpen(true);
    } else if (actionParam === 'end_of_day') {
      setEndOfDayOpen(true);
    } else if (actionParam === 'reminders' || actionParam === 'bulk_reminder') {
      setBulkReminderOpen(true);
    }
  }, [searchParams]);

  // Track if the register has been closed today — persisted in localStorage
  const todayKey = new Date().toISOString().slice(0, 10);
  const [registerClosed, setRegisterClosed] = useState<boolean>(
    localStorage.getItem('schoolbridge_register_closed_date') === todayKey
  );

  const handleRegisterClosed = () => {
    setRegisterClosed(true);
  };

  // ── Live API fetch ──────────────────────────────────────────────────────────
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['fee-records', search, currentPage, pageSize, classFilter, statusFilter],
    queryFn: async () => {
      const params: Record<string, any> = { page: currentPage, page_size: pageSize };
      if (search) params.search = search;
      if (classFilter) params.current_class = classFilter;
      if (statusFilter) params.status = statusFilter;
      const res = await apiClient.get('/payments/fee-records/', { params });
      return res.data;
    },
    staleTime: 0,
    retry: 1,
  });

  const { data: classData } = useQuery({
    queryKey: ['classes-list'],
    queryFn: async () => {
      const res = await apiClient.get('/students/classes/');
      return res.data?.results || res.data || [];
    },
    staleTime: 5 * 60 * 1000,
  });

  const classOptions = (Array.isArray(classData) ? classData : []).map((c: any) => ({
    value: String(c.id),
    label: c.name,
  }));

  const baseRecords: FeeRecord[] = data?.results || [];
  // API total count (used for server-side pagination label + Next/Prev)
  const apiTotalCount: number = data?.count ?? 0;

  // After any mutation, invalidate and actively refetch the live fee-records query
  const handlePaymentRecorded = (_studentId?: string, amount?: number) => {
    queryClient.invalidateQueries({ queryKey: ['fee-records'] });
    queryClient.refetchQueries({ queryKey: ['fee-records'] });
    queryClient.invalidateQueries({ queryKey: ['pending-payments-queue'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
    refetch();
    const amountNum = amount ? Number(amount) : 0;
    if (amountNum > 500000) {
      showToast(
        'Payment Pending Approval',
        `Payment of UGX ${amountNum.toLocaleString()} exceeds threshold and has been submitted with status 'Pending Approval'. Awaiting Director sign-off.`,
        'warning'
      );
    } else {
      const amountText = amountNum > 0 ? ` of UGX ${amountNum.toLocaleString()}` : '';
      showToast('Payment Recorded', `Payment${amountText} has been successfully recorded and receipt generated.`, 'success');
    }
  };

  const handlePaymentReversed = () => {
    queryClient.invalidateQueries({ queryKey: ['fee-records'] });
    queryClient.refetchQueries({ queryKey: ['fee-records'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
    refetch();
    showToast('Payment Reversed', 'The transaction has been reversed and balance adjusted.', 'warning');
  };

  const handlePlanCreated = () => {
    queryClient.invalidateQueries({ queryKey: ['fee-records'] });
    queryClient.refetchQueries({ queryKey: ['fee-records'] });
    refetch();
    showToast('Payment Plan Created', 'Instalment schedule configured successfully.', 'success');
  };

  const handleWaiverApplied = (_feeRecordId: string, amount: number) => {
    queryClient.invalidateQueries({ queryKey: ['fee-records'] });
    queryClient.refetchQueries({ queryKey: ['fee-records'] });
    queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
    queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
    queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
    refetch();
    if (isDirector) {
      showToast('Waiver Granted Directly', `UGX ${amount.toLocaleString()} discount has been credited to student balance.`, 'success');
    } else {
      showToast('Waiver Request Submitted', `UGX ${amount.toLocaleString()} waiver submitted for Director authorization.`, 'info');
    }
  };

  const handleWaiverApproved = (msg: string) => {
    queryClient.invalidateQueries({ queryKey: ['fee-records'] });
    queryClient.refetchQueries({ queryKey: ['fee-records'] });
    queryClient.invalidateQueries({ queryKey: ['pending-waivers-count'] });
    queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
    queryClient.invalidateQueries({ queryKey: ['fee-waivers-review'] });
    refetch();
    showToast('Waiver Approved Successfully', msg, 'success');
  };

  // ── Client-side filtering ────────────────────────────────────────────────────
  const filteredRecords = baseRecords.filter((rec) => {
    const query = search.toLowerCase().trim();
    const name = getStudentName(rec).toLowerCase();
    const studentId = getStudentCode(rec).toLowerCase();
    const matchesSearch = !query || name.includes(query) || studentId.includes(query);

    const balance = getNum(rec.balance);
    const paid = getNum(rec.amount_paid);

    const matchesStatus = (() => {
      if (!statusFilter) return true;
      if (statusFilter === 'cleared') return (balance <= 0 || rec.is_fully_paid) && !rec.has_pending_waiver && !rec.has_pending_payment;
      if (statusFilter === 'pending_approval') return !!rec.has_pending_waiver || !!rec.has_pending_payment;
      if (statusFilter === 'partial_plan') return !!rec.has_payment_plan && balance > 0;
      if (statusFilter === 'partial') return paid > 0 && balance > 0 && !rec.has_payment_plan;
      if (statusFilter === 'unpaid') return paid === 0 && balance > 0;
      if (statusFilter === 'defaulter') return balance > 0;
      return getStatus(rec) === statusFilter;
    })();

    return matchesSearch && matchesStatus;
  });


  // ── KPI calculations (live from displayed records) ───────────────────────────
  const totalBilled = baseRecords.reduce((s, r) => s + getNum(r.total_amount), 0);
  const totalCollected = baseRecords.reduce((s, r) => s + getNum(r.amount_paid), 0);
  const totalOutstanding = baseRecords.reduce((s, r) => s + getNum(r.balance), 0);
  const highRiskCount = baseRecords.filter(r => getNum(r.escalation_level) >= 3).length;
  const clearedCount = baseRecords.filter(r => getNum(r.balance) <= 0 || r.is_fully_paid).length;
  const collectionRate = totalBilled > 0
    ? Math.round((totalCollected / totalBilled) * 100)
    : (totalCollected + totalOutstanding > 0 ? Math.round((totalCollected / (totalCollected + totalOutstanding)) * 100) : 0);

  // ── Columns ──────────────────────────────────────────────────────────────────
  const columns: Column<FeeRecord>[] = [
    {
      header: 'Student',
      cell: (row) => (
        <div>
          <p className="text-xs font-semibold text-white">
            {getStudentName(row)}
          </p>
          <span className="text-[10px] font-mono text-emerald-400">{getStudentCode(row)}</span>
        </div>
      ),
    },
    {
      header: 'Class',
      cell: (row) => (
        <span className="text-xs text-slate-300">{getClassName(row)}</span>
      ),
    },
    {
      header: 'Total Fees',
      cell: (row) => (
        <span className="text-xs font-mono text-slate-300">{fmt(getNum(row.total_amount))}</span>
      ),
    },
    {
      header: 'Paid',
      cell: (row) => {
        const paid = getNum(row.amount_paid);
        const waived = getNum(row.amount_waived);
        return (
          <div>
            <span className="text-xs font-mono text-emerald-400 font-semibold">{fmt(paid)}</span>
            {waived > 0 && (
              <p className="text-[9px] text-indigo-400 mt-0.5">+{fmt(waived)} waived</p>
            )}
          </div>
        );
      },
    },
    {
      header: 'Balance',
      cell: (row) => {
        const balance = getNum(row.balance);
        return (
          <span className={`text-xs font-mono font-bold ${balance > 0 ? 'text-amber-400' : 'text-slate-500'}`}>
            {balance > 0 ? fmt(balance) : '—'}
          </span>
        );
      },
    },
    {
      header: 'Status',
      cell: (row) => {
        const status = getStatus(row);
        const cfg = STATUS_CONFIG[status];
        const escalation = getNum(row.escalation_level);
        const isEscalated = escalation >= 3;
        const label = status === 'partial_plan'
          ? 'Partial (Plan)'
          : cfg.label;
        return (
          <div className="flex flex-col gap-0.5">
            <Badge variant={cfg.variant} size="sm">{label}</Badge>
            {/* Show escalation warning as sub-label when partial/plan-active but also escalated */}
            {isEscalated && (status === 'partial' || status === 'partial_plan' || status === 'unpaid') && (
              <span className="text-[9px] text-rose-400 font-mono font-semibold">
                Level {escalation} escalated
              </span>
            )}
            {status === 'pending_approval' && row.pending_payment_amount ? (
              <span className="text-[9px] text-amber-400 font-mono font-medium">
                UGX {getNum(row.pending_payment_amount).toLocaleString()} payment
              </span>
            ) : status === 'pending_approval' && row.pending_waiver_amount ? (
              <span className="text-[9px] text-amber-400 font-mono font-medium">
                UGX {getNum(row.pending_waiver_amount).toLocaleString()} waiver
              </span>
            ) : status === 'cleared' ? (
              <span className="text-[9px] text-emerald-400/90 font-mono font-medium">
                {row.clearance_date ? `Cleared ${row.clearance_date}` : row.last_payment_date ? `Cleared ${row.last_payment_date}` : 'Fully Settled'}
              </span>
            ) : row.last_payment_date && !isEscalated ? (
              <span className="text-[9px] text-slate-500 font-mono">Last paid {row.last_payment_date}</span>
            ) : null}
          </div>
        );
      },
    },
    {
      header: 'Actions',
      cell: (row) => {
        const status = getStatus(row);
        const isCleared = status === 'cleared';
        const studentName = getStudentName(row);
        const balance = getNum(row.balance);

        // ── Business rule: All actions locked when balance is zero ──────────
        if (isCleared) {
          return (
            <div className="flex items-center gap-1.5">
              <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-semibold mr-2">
                <CheckCircle2 className="w-3.5 h-3.5" /> Fully Cleared
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="text-[11px] py-1 px-2.5 text-slate-400 hover:text-white"
                onClick={() => {
                  setSelectedFeeRecord(row);
                  setLedgerModalOpen(true);
                }}
                title="View Ledger & History"
              >
                Ledger
              </Button>
            </div>
          );
        }

        return (
          <div className="flex items-center gap-1.5">
            {/* PAY */}
            <Button
              variant="secondary"
              size="sm"
              className="text-[11px] py-1 px-2.5"
              leftIcon={<Banknote className="w-3 h-3 text-emerald-400" />}
              onClick={() => {
                setSelectedFeeRecord(row);
                setRecordModalOpen(true);
              }}
              title={`Record cash/bank payment for ${studentName}`}
            >
              Pay
            </Button>

            {/* PLAN — shows "View Plan" if plan exists, "Plan" if none */}
            <Button
              variant="secondary"
              size="sm"
              className="text-[11px] py-1 px-2.5"
              leftIcon={
                row.has_payment_plan
                  ? <Eye className="w-3 h-3 text-indigo-400" />
                  : <Calendar className="w-3 h-3 text-indigo-400" />
              }
              onClick={() => {
                setSelectedFeeRecord(row);
                setPlanModalOpen(true);
              }}
              title={
                row.has_payment_plan
                  ? `View / edit instalment plan (${row.payment_plan_installments} instalments)`
                  : 'Create new instalment plan'
              }
            >
              {row.has_payment_plan ? 'View Plan' : 'Plan'}
            </Button>

            {/* LINK — MoMo payment link */}
            <Button
              variant="secondary"
              size="sm"
              className="text-[11px] py-1 px-2.5 text-teal-300"
              leftIcon={<Link2 className="w-3 h-3 text-teal-400" />}
              onClick={() => {
                setSelectedFeeRecord(row);
                setLinkModalOpen(true);
              }}
              title={`Generate MoMo payment link for UGX ${balance.toLocaleString()}`}
            >
              Link
            </Button>

            {/* WAIVER — role-gated: Director sees approval interface, Bursar sees submission form */}
            <Button
              variant={row.has_pending_waiver ? 'secondary' : 'ghost'}
              size="sm"
              className={`text-[11px] py-1 px-2.5 ${
                row.has_pending_waiver
                  ? 'text-amber-300 border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 font-semibold shadow-sm'
                  : 'text-amber-400 hover:text-amber-300'
              }`}
              onClick={() => {
                setSelectedFeeRecord(row);
                if (isDirector || row.has_pending_waiver) {
                  // If a waiver is already pending or user is Director, open review modal
                  setReviewWaiversOpen(true);
                } else {
                  // Bursars submit waiver requests for Director approval
                  setWaiverModalOpen(true);
                }
              }}
              title={
                row.has_pending_waiver
                  ? `Pending waiver of UGX ${getNum(row.pending_waiver_amount).toLocaleString()} awaiting Director review`
                  : isDirector
                    ? 'Review & approve/reject pending waivers'
                    : 'Request fee discount / bursary'
              }
            >
              {row.has_pending_waiver ? 'Pending Approval' : 'Request Waiver'}
            </Button>

            {/* LEDGER — view full payment history & reversals */}
            <Button
              variant={row.has_pending_payment ? 'secondary' : 'ghost'}
              size="sm"
              className={`text-[11px] py-1 px-2.5 ${
                row.has_pending_payment
                  ? 'text-amber-300 border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              onClick={() => {
                setSelectedFeeRecord(row);
                setLedgerModalOpen(true);
              }}
              title={
                row.has_pending_payment
                  ? isDirector
                    ? `Payment of UGX ${getNum(row.pending_payment_amount).toLocaleString()} awaiting your approval — click to review & approve`
                    : `Payment of UGX ${getNum(row.pending_payment_amount).toLocaleString()} awaiting Director approval`
                  : 'View Ledger & History'
              }
            >
              {row.has_pending_payment ? (isDirector ? 'Review Payment' : 'Pending Payment') : 'Ledger'}
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Fee Collection & Revenue</h1>
          <p className="text-xs text-slate-400 mt-1">
            Manage fee accounts, record payments, and configure instalment plans
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <PendingPaymentsBadge isDirector={isDirector} onClick={() => setStatusFilter('pending_approval')} />
          <PendingWaiversBadge onClick={() => setReviewWaiversOpen(true)} />
          <Link to="/finance/reconciliation">
            <Button variant="secondary" size="sm" rightIcon={<ArrowRight className="w-4 h-4" />}>
              MoMo Reconciliation Queue
            </Button>
          </Link>
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Megaphone className="w-4 h-4 text-emerald-400" />}
            onClick={() => setBulkReminderOpen(true)}
          >
            Broadcast Fee Reminders
          </Button>
          {registerClosed ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEndOfDayOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 rounded-lg text-xs font-semibold text-emerald-400 transition-colors"
            >
              <CheckCircle2 className="w-3.5 h-3.5" /> Register Closed (View Summary)
            </Button>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setEndOfDayOpen(true)}
            >
              End of Day
            </Button>
          )}
          <RbacGate permission="payment:record">
            <Button
              variant="primary"
              size="sm"
              leftIcon={<CreditCard className="w-4 h-4" />}
              onClick={() => {
                setSelectedFeeRecord(null);
                setRecordModalOpen(true);
              }}
            >
              Record Cash Payment
            </Button>
          </RbacGate>
        </div>
      </div>

      {/* ── Section Tabs ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-1">
        <button
          type="button"
          onClick={() => setMainTab('accounts')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-xs transition-all ${
            mainTab === 'accounts'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
          }`}
        >
          <CreditCard className="w-4 h-4" />
          <span>Fee Collection & Accounts</span>
        </button>

        <button
          type="button"
          onClick={() => setMainTab('structures')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-xs transition-all ${
            mainTab === 'structures'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Fee Structures</span>
        </button>
      </div>

      {/* ── Director Approval Queue (always visible, any tab) ─────────────── */}
      <ApprovalQueueBanner
        isDirector={isDirector}
        onPaymentApproved={(studentName, amount) => {
          refetch();
          showToast('Payment Approved', `UGX ${amount.toLocaleString()} applied to ${studentName}'s balance.`, 'success');
        }}
        onWaiverApproved={(studentName, amount) => {
          refetch();
          showToast('Waiver Approved', `UGX ${amount.toLocaleString()} discount applied to ${studentName}'s balance.`, 'success');
        }}
        onOpenWaiversModal={() => setReviewWaiversOpen(true)}
      />

      {mainTab === 'structures' ? (
        <FeeStructuresTab onSuccessToast={(title, msg) => showToast(title, msg, 'success')} />
      ) : (
        <>

          {/* ── KPI Summary Cards ────────────────────────────────────────── */}
          <StatGroup>
            <KpiCard
              title="Total Fees Billed"
              value={fmt(totalBilled)}
              subtitle={`${apiTotalCount || baseRecords.length} Student Accounts`}
              changeType="neutral"
              icon={<Banknote className="w-5 h-5 text-indigo-400" />}
              isActive={statusFilter === ''}
              onClick={() => {
                setStatusFilter('');
                setCurrentPage(1);
              }}
              clickableHint="Show all"
            />
            <KpiCard
              title="Total Collected"
              value={fmt(totalCollected)}
              subtitle={`${collectionRate}% Overall Collection Rate (${clearedCount} Cleared)`}
              changeType="positive"
              icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />}
              isActive={statusFilter === 'cleared'}
              onClick={() => {
                setStatusFilter('cleared');
                setCurrentPage(1);
              }}
              clickableHint="Filter cleared"
            />
            <KpiCard
              title="Outstanding Balance"
              value={fmt(totalOutstanding)}
              subtitle={`${baseRecords.filter((r) => getNum(r.balance) > 0).length} Accounts with Balance`}
              changeType={totalOutstanding > 0 ? "negative" : "positive"}
              icon={<CreditCard className="w-5 h-5 text-amber-400" />}
              isActive={statusFilter === 'partial'}
              onClick={() => {
                setStatusFilter('partial');
                setCurrentPage(1);
              }}
              clickableHint="Filter with balance"
            />
            <KpiCard
              title="At-Risk Accounts"
              value={String(highRiskCount)}
              subtitle="Escalation Level 3+ (Defaulters)"
              changeType={highRiskCount > 0 ? "negative" : "neutral"}
              icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
              isActive={statusFilter === 'defaulter'}
              onClick={() => {
                setStatusFilter('defaulter');
                setCurrentPage(1);
              }}
              clickableHint="Filter defaulters"
            />
          </StatGroup>

          {/* ── Filters & Actions Bar ──────────────────────────────────────── */}
          <FilterBar
            searchValue={search}
            onSearchChange={(val) => {
              setSearch(val);
              setCurrentPage(1);
            }}
            searchPlaceholder="Search student name or admission code..."
            onResetAll={() => {
              setSearch('');
              setStatusFilter('');
              setClassFilter('');
              setCurrentPage(1);
            }}
          >
            <div className="w-44">
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Payment Statuses</option>
                <option value="cleared">Cleared (Fully Paid)</option>
                <option value="partial_plan">Partial (Active Plan)</option>
                <option value="partial">Partial (No Plan)</option>
                <option value="unpaid">Unpaid (Zero Paid)</option>
                <option value="defaulter">Defaulters & Reminders (Arrears)</option>
                <option value="pending_approval">Pending Approval (Waiver / Payment)</option>
              </select>
            </div>

            <div className="w-40">
              <select
                value={classFilter}
                onChange={(e) => {
                  setClassFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Classes</option>
                {classOptions.map((c: any) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Megaphone className="w-3.5 h-3.5 text-indigo-400" />}
              onClick={() => setBulkReminderOpen(true)}
            >
              Bulk Reminders
            </Button>
          </FilterBar>

          {/* ── Defaulter Focus Banner ───────────────────────────────────── */}
          {statusFilter === 'defaulter' && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>
                  <strong>Defaulter Tracking Active:</strong> Showing all student fee accounts with overdue balances.
                </span>
              </div>
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<Megaphone className="w-3.5 h-3.5 text-rose-400" />}
                onClick={() => setBulkReminderOpen(true)}
                className="border-rose-500/30 text-rose-200 hover:bg-rose-500/20"
              >
                Dispatch Defaulter Reminders
              </Button>
            </div>
          )}

          {/* ── Fee Records Table ────────────────────────────────────────── */}
          <DataTable
            columns={columns}
            data={filteredRecords}
            isLoading={isLoading}
            emptyMessage="No fee records match your query."
          />

          {/* ── Pagination ──────────────────────────────────────────────── */}
          {(() => {
            const paginatorTotal = statusFilter
              ? filteredRecords.length
              : (apiTotalCount || filteredRecords.length);
            return (
              filteredRecords.length > 0 && (
                <TablePagination
                  currentPage={currentPage}
                  totalCount={paginatorTotal}
                  pageSize={pageSize}
                  onPageChange={setCurrentPage}
                  onPageSizeChange={(sz) => {
                    setPageSize(sz);
                    setCurrentPage(1);
                  }}
                />
              )
            );
          })()}
        </>
      )}

      {/* ── Modals ──────────────────────────────────────────────────────────── */}
      <RecordPaymentModal
        isOpen={recordModalOpen}
        onClose={() => {
          setRecordModalOpen(false);
          setSelectedFeeRecord(null);
        }}
        feeRecordId={selectedFeeRecord?.id}
        initialStudentId={selectedFeeRecord ? getStudentId(selectedFeeRecord) : undefined}
        studentCode={selectedFeeRecord ? getStudentCode(selectedFeeRecord) : undefined}
        className={selectedFeeRecord ? getClassName(selectedFeeRecord) : undefined}
        initialStudentName={selectedFeeRecord ? getStudentName(selectedFeeRecord) : undefined}
        initialBalance={selectedFeeRecord ? getNum(selectedFeeRecord.balance) : undefined}
        onPaymentRecorded={handlePaymentRecorded}
      />

      {selectedFeeRecord && (
        <>
          <PaymentPlanModal
            isOpen={planModalOpen}
            onClose={() => setPlanModalOpen(false)}
            feeRecordId={selectedFeeRecord.id}
            studentId={getStudentId(selectedFeeRecord)}
            studentCode={getStudentCode(selectedFeeRecord)}
            className={getClassName(selectedFeeRecord)}
            studentName={getStudentName(selectedFeeRecord)}
            totalBalance={getNum(selectedFeeRecord.balance)}
            hasExistingPlan={!!selectedFeeRecord.has_payment_plan}
            onPlanCreated={handlePlanCreated}
          />

          <PaymentLinkModal
            isOpen={linkModalOpen}
            onClose={() => setLinkModalOpen(false)}
            feeRecordId={selectedFeeRecord.id}
            studentId={getStudentId(selectedFeeRecord)}
            studentCode={getStudentCode(selectedFeeRecord)}
            className={getClassName(selectedFeeRecord)}
            studentName={getStudentName(selectedFeeRecord)}
            defaultAmount={getNum(selectedFeeRecord.balance)}
          />

          <PaymentLedgerDrawer
            isOpen={ledgerModalOpen}
            onClose={() => setLedgerModalOpen(false)}
            feeRecordId={selectedFeeRecord.id}
            studentId={getStudentId(selectedFeeRecord)}
            studentCode={getStudentCode(selectedFeeRecord)}
            studentName={getStudentName(selectedFeeRecord)}
            className={getClassName(selectedFeeRecord)}
            totalAmount={getNum(selectedFeeRecord.total_amount)}
            amountPaid={getNum(selectedFeeRecord.amount_paid)}
            amountWaived={getNum(selectedFeeRecord.amount_waived)}
            balance={getNum(selectedFeeRecord.balance)}
            hasPaymentPlan={Boolean(selectedFeeRecord.has_payment_plan)}
            onPaymentReversed={handlePaymentReversed}
          />
        </>
      )}

      <BulkReminderModal
        isOpen={bulkReminderOpen}
        onClose={() => setBulkReminderOpen(false)}
        onSent={(count) =>
          showToast(
            'Broadcast Campaign Dispatched',
            `${count} personalised reminder${count !== 1 ? 's' : ''} queued for delivery via WhatsApp/SMS.`,
            'success',
          )
        }
      />

      <EndOfDayModal
        isOpen={endOfDayOpen}
        onClose={() => setEndOfDayOpen(false)}
        onRegisterClosed={handleRegisterClosed}
      />

      {selectedFeeRecord && (
        <ApplyWaiverModal
          isOpen={waiverModalOpen}
          onClose={() => setWaiverModalOpen(false)}
          feeRecordId={selectedFeeRecord.id}
          studentCode={getStudentCode(selectedFeeRecord)}
          className={getClassName(selectedFeeRecord)}
          studentName={getStudentName(selectedFeeRecord)}
          totalAmount={getNum(selectedFeeRecord.total_amount)}
          amountPaid={getNum(selectedFeeRecord.amount_paid)}
          amountWaived={getNum(selectedFeeRecord.amount_waived)}
          balance={getNum(selectedFeeRecord.balance)}
          isDirector={isDirector}
          onWaiverApplied={handleWaiverApplied}
        />
      )}

      <ReviewWaiversModal
        isOpen={reviewWaiversOpen}
        onClose={() => { setReviewWaiversOpen(false); }}
        isDirector={isDirector}
        highlightStudentName={selectedFeeRecord ? getStudentName(selectedFeeRecord) : undefined}
        onWaiverApproved={handleWaiverApproved}
      />

      {/* ── Global Floating Toast Notification ───────────────────────────── */}
      {toast && toast.show && (
        <div className="fixed top-6 right-6 z-50 max-w-md animate-in slide-in-from-top duration-300">
          <div
            className={`p-4 rounded-xl border shadow-2xl flex items-start gap-3 backdrop-blur-md ${
              toast.type === 'success'
                ? 'bg-emerald-950/95 border-emerald-500/40 text-emerald-100 shadow-emerald-900/40'
                : toast.type === 'warning'
                ? 'bg-amber-950/95 border-amber-500/40 text-amber-100 shadow-amber-900/40'
                : 'bg-cyan-950/95 border-cyan-500/40 text-cyan-100 shadow-cyan-900/40'
            }`}
          >
            <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 shrink-0 mt-0.5">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <h4 className="font-bold text-sm text-white">{toast.title}</h4>
              <p className="text-xs text-slate-200 mt-0.5 leading-relaxed">{toast.message}</p>
            </div>
            <button
              onClick={() => setToast(null)}
              className="text-slate-400 hover:text-white text-xs p-1"
              aria-label="Close notification"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
