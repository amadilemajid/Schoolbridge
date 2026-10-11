import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { CurrencyInput } from '../ui/CurrencyInput';
import { TextInput } from '../ui/TextInput';
import { Calendar, Plus, Trash2, CheckCircle2, AlertTriangle, Eye, PlusCircle } from 'lucide-react';

interface InstalmentInput {
  due_date: string;
  amount: number;
}

interface ExistingInstalment {
  id: string;
  instalment_number: number;
  amount: number;
  due_date: string;
  paid_date: string | null;
  status: 'pending' | 'partial' | 'paid' | 'overdue' | 'waived';
}

interface ExistingPlan {
  id: string;
  total_amount: number;
  status: 'active' | 'completed' | 'defaulted' | 'cancelled';
  instalments: ExistingInstalment[];
  created_at: string;
}

interface PaymentPlanModalProps {
  isOpen: boolean;
  onClose: () => void;
  feeRecordId?: string;
  studentId: string;
  studentCode?: string;
  className?: string;
  studentName: string;
  totalBalance: number;
  hasExistingPlan?: boolean;
  onPlanCreated?: (studentId: string) => void;
}

const INSTALMENT_STATUS_STYLES: Record<string, string> = {
  pending: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  partial: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  paid: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  overdue: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
  waived: 'text-slate-400 bg-slate-500/10 border-slate-500/30',
};

export const PaymentPlanModal: React.FC<PaymentPlanModalProps> = ({
  isOpen,
  onClose,
  feeRecordId,
  studentId,
  studentCode,
  className,
  studentName,
  totalBalance,
  hasExistingPlan = false,
  onPlanCreated,
}) => {
  const queryClient = useQueryClient();

  // 'view' = showing existing plan | 'create' = creating new plan form
  const [mode, setMode] = useState<'view' | 'create'>('view');
  const [error, setError] = useState<string | null>(null);

  const getBlankInstalments = (): InstalmentInput[] => {
    const half = Math.round(totalBalance / 2);
    return [
      { due_date: '', amount: half },
      { due_date: '', amount: totalBalance - half },
    ];
  };

  const [instalments, setInstalments] = useState<InstalmentInput[]>(getBlankInstalments);

  // Sync state when modal opens or mode changes
  React.useEffect(() => {
    if (isOpen) {
      setError(null);
      if (hasExistingPlan) {
        setMode('view');
      } else {
        setMode('create');
        setInstalments(getBlankInstalments());
      }
    }
  }, [isOpen, hasExistingPlan, totalBalance]);

  // Fetch the existing plan from the API when in 'view' mode
  const { data: existingPlanData, isLoading: planLoading } = useQuery<ExistingPlan | null>({
    queryKey: ['payment-plan', feeRecordId],
    queryFn: async () => {
      if (!feeRecordId) return null;
      const res = await apiClient.get('/payments/payment-plans/', {
        params: { fee_record: feeRecordId },
      });
      const results = res.data?.results || res.data || [];
      return results[0] || null;
    },
    enabled: isOpen && hasExistingPlan,
  });

  const sumInstalments = instalments.reduce((acc, curr) => acc + (curr.amount || 0), 0);
  const isValidSum = sumInstalments === totalBalance;

  const { mutate: createPlan, isPending } = useMutation({
    mutationFn: async () => {
      const payload = {
        fee_record: feeRecordId || studentId,
        total_amount: totalBalance,
        instalments,
      };
      const res = await apiClient.post('/payments/payment-plans/', payload);
      return res.data;
    },
    onSuccess: () => {
      if (onPlanCreated) {
        onPlanCreated(studentId);
      }
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.invalidateQueries({ queryKey: ['payment-plan', feeRecordId] });
      onClose();
    },
    onError: (err: any) => {
      if (!err.response) {
        setError('Connection error: Unable to reach the server. Please check your internet connection and try again.');
        return;
      }
      const data = err.response?.data;
      const detail = data?.detail ?? data?.error ?? data;
      const msg = typeof detail === 'string'
        ? detail
        : typeof detail === 'object' && detail !== null
          ? Object.entries(detail).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' • ')
          : 'Failed to create payment plan. Please try again.';
      setError(msg || 'Failed to create payment plan. Please try again.');
    },
  });

  const handleAddInstalment = () => {
    if (instalments.length >= 4) return;
    setInstalments((prev) => [...prev, { due_date: '', amount: 0 }]);
  };

  const handleRemoveInstalment = (index: number) => {
    if (instalments.length <= 2) return;
    setInstalments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpdate = (index: number, field: keyof InstalmentInput, value: any) => {
    setInstalments((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const todayStr = new Date().toISOString().slice(0, 10);

    if (instalments.some((i) => !i.due_date)) {
      setError('Please select a due date for all instalments.');
      return;
    }
    if (instalments.some((i) => (i.amount || 0) <= 0)) {
      setError('Each instalment amount must be greater than UGX 0.');
      return;
    }
    if (instalments.some((i) => i.due_date < todayStr)) {
      setError('Instalment due dates cannot be in the past. Please choose future due dates.');
      return;
    }
    for (let i = 1; i < instalments.length; i++) {
      if (instalments[i].due_date <= instalments[i - 1].due_date) {
        setError(
          `Invalid date sequence: Instalment #${i + 1} due date (${instalments[i].due_date}) must be after Instalment #${i} due date (${instalments[i - 1].due_date}).`
        );
        return;
      }
    }
    if (!isValidSum) {
      setError(
        `Sum of instalments (UGX ${sumInstalments.toLocaleString()}) must equal the total outstanding balance (UGX ${totalBalance.toLocaleString()}).`
      );
      return;
    }

    createPlan();
  };

  const planStatus = existingPlanData?.status;
  const planStatusStyle =
    planStatus === 'completed'
      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
      : planStatus === 'defaulted'
      ? 'text-rose-400 bg-rose-500/10 border-rose-500/30'
      : 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        mode === 'view'
          ? 'Active Instalment Payment Plan'
          : hasExistingPlan
          ? 'Attempt: Create New Plan (Duplicate Test)'
          : 'Create Instalment Payment Plan'
      }
      description={
        mode === 'view'
          ? 'Live instalment schedule fetched from the database'
          : hasExistingPlan
          ? 'Edge Case 7: This will be rejected by the backend as a duplicate active plan.'
          : 'US-C05: Set up 2 to 4 structured payment instalments with automated reminder triggers'
      }
      maxWidth="xl"
    >
      <div className="space-y-4">
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Student Balance Header */}
        <div className="p-4 bg-slate-800 rounded-xl border border-slate-700 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-white">{studentName}</p>
            <p className="text-[10px] font-mono text-emerald-400">
              {studentCode || studentId} {className ? `• ${className}` : ''}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wider">Outstanding Balance</p>
            <p className="text-sm font-bold text-emerald-400">UGX {totalBalance.toLocaleString()}</p>
          </div>
        </div>

        {/* ---- VIEW MODE: Show the existing live plan ---- */}
        {mode === 'view' && (
          <>
            {planLoading ? (
              <div className="p-8 text-center text-slate-500 text-xs">Loading plan from database…</div>
            ) : existingPlanData ? (
              <>
                {/* Plan status banner */}
                <div className={`px-3 py-2 rounded-xl border text-xs font-semibold flex items-center justify-between ${planStatusStyle}`}>
                  <span>Plan Status: {existingPlanData.status.toUpperCase()}</span>
                  <span className="font-mono opacity-80">Total: UGX {Number(existingPlanData.total_amount).toLocaleString()}</span>
                </div>

                {/* Instalment rows */}
                <div className="space-y-2">
                  <p className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Instalment Schedule ({existingPlanData.instalments.length} total)
                  </p>
                  {existingPlanData.instalments.map((inst) => {
                    return (
                      <div
                        key={inst.id}
                        className="p-3 bg-slate-800 border border-slate-700 rounded-xl flex items-center justify-between gap-3 text-xs"
                      >
                        <span className="text-slate-400 font-semibold w-6 shrink-0">#{inst.instalment_number}</span>
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-white">UGX {Number(inst.amount).toLocaleString()}</p>
                          <p className="text-slate-500">Due: {inst.due_date}</p>
                          {inst.paid_date && (
                            <p className="text-emerald-400 text-[10px]">Paid: {new Date(inst.paid_date).toLocaleDateString()}</p>
                          )}
                        </div>
                        <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider ${INSTALMENT_STATUS_STYLES[inst.status] || ''}`}>
                          {inst.status}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Edge-case 7 tester button */}
                {planStatus === 'active' && (
                  <div className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-xl text-[11px] text-amber-400">
                    <p className="font-semibold mb-1 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> Edge Case 7: Duplicate Plan Test</p>
                    <p className="text-slate-400">An active plan already exists. Click below to attempt creating a new plan — the system must reject it.</p>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="mt-2 text-amber-400 border-amber-500/30"
                      leftIcon={<PlusCircle className="w-3.5 h-3.5" />}
                      onClick={() => {
                        setInstalments(getBlankInstalments());
                        setError(null);
                        setMode('create');
                      }}
                    >
                      Attempt to Create Duplicate Plan
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <div className="p-6 text-center text-slate-500 text-xs">No plan data found.</div>
            )}

            <div className="flex justify-end pt-4 border-t border-slate-800">
              <Button type="button" variant="secondary" onClick={onClose}>Close</Button>
            </div>
          </>
        )}

        {/* ---- CREATE MODE: Form to create / attempt duplicate ---- */}
        {mode === 'create' && (
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Instalments List */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                  Instalments Schedule ({instalments.length} / 4)
                </p>
                {instalments.length < 4 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    leftIcon={<Plus className="w-3.5 h-3.5" />}
                    onClick={handleAddInstalment}
                  >
                    Add Instalment
                  </Button>
                )}
              </div>

              {instalments.map((item, idx) => (
                <div
                  key={idx}
                  className="p-3.5 bg-slate-850 border border-slate-700/60 rounded-xl grid grid-cols-1 sm:grid-cols-12 gap-3 items-center"
                >
                  <span className="sm:col-span-2 text-xs font-semibold text-slate-400"># {idx + 1}</span>
                  <div className="sm:col-span-5">
                    <TextInput
                      type="date"
                      label={`Due Date #${idx + 1}`}
                      value={item.due_date}
                      min={new Date().toISOString().slice(0, 10)}
                      onChange={(e) => handleUpdate(idx, 'due_date', e.target.value)}
                      required
                    />
                  </div>
                  <div className="sm:col-span-4">
                    <CurrencyInput
                      label={`Amount #${idx + 1}`}
                      value={item.amount}
                      onChange={(val) => handleUpdate(idx, 'amount', val)}
                      required
                    />
                  </div>
                  <div className="sm:col-span-1 flex justify-end pt-5">
                    {instalments.length > 2 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveInstalment(idx)}
                        className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Sum Check */}
            <div
              className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
                isValidSum
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
              }`}
            >
              <span>
                Current Total: <strong>UGX {sumInstalments.toLocaleString()}</strong>
              </span>
              <span>
                {isValidSum ? (
                  <span className="flex items-center gap-1 text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-4 h-4" /> Balanced
                  </span>
                ) : (
                  <span>Difference: UGX {Math.abs(totalBalance - sumInstalments).toLocaleString()}</span>
                )}
              </span>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
              {hasExistingPlan && (
                <Button
                  type="button"
                  variant="secondary"
                  leftIcon={<Eye className="w-4 h-4" />}
                  onClick={() => { setError(null); setMode('view'); }}
                >
                  Back to View Plan
                </Button>
              )}
              <Button type="button" variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                isLoading={isPending}
                disabled={!isValidSum}
                leftIcon={<Calendar className="w-4 h-4" />}
              >
                {hasExistingPlan ? 'Send Duplicate (Expect Rejection)' : 'Save Payment Plan Schedule'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
};
