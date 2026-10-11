import React, { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { CurrencyInput } from '../ui/CurrencyInput';
import { Select } from '../ui/Select';
import { CreditCard, MessageSquare, Search, User, X, Loader2, ShieldAlert } from 'lucide-react';

interface RecordPaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  feeRecordId?: string;
  initialStudentId?: string;
  studentCode?: string;
  className?: string;
  initialStudentName?: string;
  initialBalance?: number;
  onPaymentRecorded?: (studentId: string, amount: number) => void;
}

const DEFAULT_PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash Payment' },
  { value: 'bank', label: 'Bank Direct Deposit' },
  { value: 'mtn_momo', label: 'MTN Mobile Money' },
  { value: 'airtel_money', label: 'Airtel Money' },
  { value: 'momo', label: 'Other Mobile Money' },
];

export const RecordPaymentModal: React.FC<RecordPaymentModalProps> = ({
  isOpen,
  onClose,
  feeRecordId = '',
  initialStudentId = '',
  studentCode = '',
  className = '',
  initialStudentName = '',
  initialBalance = 0,
  onPaymentRecorded,
}) => {
  const queryClient = useQueryClient();
  const [studentSearch, setStudentSearch] = useState(initialStudentName);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  const [amount, setAmount] = useState<number | ''>('');
  const [method, setMethod] = useState('cash');
  const [reference, setReference] = useState('');
  const [payerName, setPayerName] = useState('');
  const [notes, setNotes] = useState('');
  const [sendWhatsAppReceipt, setSendWhatsAppReceipt] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch dynamic system metadata (payment methods, currency, school details) from backend
  const { data: metadata } = useQuery({
    queryKey: ['system-metadata'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/metadata/');
        return res.data;
      } catch (err) {
        return null;
      }
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const currency = metadata?.currency || 'UGX';
  const paymentMethods =
    metadata?.payment_methods && metadata.payment_methods.length > 0
      ? metadata.payment_methods
      : DEFAULT_PAYMENT_METHODS;

  // Debounce search input to avoid spamming the backend while typing
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(studentSearch.trim());
    }, 200);
    return () => clearTimeout(timer);
  }, [studentSearch]);

  // Dynamic live search against backend fee records and student registry
  const { data: searchResults = [], isFetching: isSearching } = useQuery({
    queryKey: ['fee-records-search', debouncedSearch],
    queryFn: async () => {
      const params: Record<string, any> = { page_size: 20 };
      if (debouncedSearch) {
        params.search = debouncedSearch;
      }
      const res = await apiClient.get('/payments/fee-records/', { params });
      const records: any[] = Array.isArray(res.data) ? res.data : (res.data?.results || []);

      // If searching and fewer than 3 records found, also query student lookups for enrolled students without fee records
      if (debouncedSearch && records.length < 3) {
        try {
          const studentRes = await apiClient.get('/metadata/lookups/students/', {
            params: { search: debouncedSearch },
          });
          const students = Array.isArray(studentRes.data) ? studentRes.data : (studentRes.data?.results || []);
          const existingStudentIds = new Set(
            records.map((r: any) => (typeof r.student === 'object' ? r.student?.id : r.student))
          );
          for (const st of students) {
            if (!existingStudentIds.has(st.id)) {
              records.push({
                id: st.id,
                is_student_fallback: true,
                student: st.id,
                student_name: st.full_name,
                student_id_code: st.student_id,
                class_name: st.class_name,
                balance: 0,
                total_amount: 0,
                amount_paid: 0,
              });
            }
          }
        } catch {
          // Ignore student lookup error
        }
      }
      return records;
    },
    enabled: isOpen && !initialStudentName,
    staleTime: 10000,
  });

  // Reset form state whenever modal opens so stale errors/amounts never persist
  useEffect(() => {
    if (isOpen) {
      setAmount('');
      setReference('');
      setPayerName('');
      setNotes('');
      setError(null);
      setMethod('cash');
      setStudentSearch(initialStudentName);
      setSelectedRecord(null);
      setDropdownOpen(false);
    }
  }, [isOpen, initialStudentId, feeRecordId, initialStudentName]);

  // Click outside listener for student search dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const activeStudentName =
    initialStudentName ||
    (selectedRecord
      ? selectedRecord.student_name ||
        (typeof selectedRecord.student === 'object'
          ? `${selectedRecord.student.first_name} ${selectedRecord.student.last_name}`
          : '')
      : '');
  const activeStudentCode =
    studentCode ||
    (selectedRecord ? selectedRecord.student_id_code || selectedRecord.student?.student_id || '' : '');
  const activeClassName =
    className ||
    (selectedRecord
      ? selectedRecord.class_name || selectedRecord.student?.current_class?.name || ''
      : '');
  const activeBalance = initialStudentName
    ? initialBalance
    : selectedRecord
    ? Number(selectedRecord.balance || 0)
    : 0;
  const activeRecordId = feeRecordId || selectedRecord?.id || '';

  const { mutate: recordPayment, isPending } = useMutation({
    mutationFn: async (resolvedRecordId?: string) => {
      // Priority: direct fee record UUID / student ID > typed student ID > initialStudentId
      const recordRef = resolvedRecordId || activeRecordId || studentSearch;
      const payload = {
        fee_record: recordRef,
        fee_record_id: recordRef,
        amount: amount === '' ? 0 : Number(amount),
        method,
        receipt_number: reference || '',
        payer_name: payerName || '',
        notes: notes.trim(),
        bank_reference: method === 'bank' ? reference || '' : '',
        send_receipt: sendWhatsAppReceipt,
      };
      const res = await apiClient.post('/payments/payments/', payload);
      return res.data;
    },
    onSuccess: (_data: any) => {
      const targetId = activeRecordId || initialStudentId || feeRecordId;
      const numAmount = amount === '' ? 0 : Number(amount);
      if (onPaymentRecorded) {
        onPaymentRecorded(targetId, numAmount);
      }
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records-search'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
      queryClient.invalidateQueries({ queryKey: ['student-payments'] });
      queryClient.invalidateQueries({ queryKey: ['pending-payments'] });
      onClose();
      resetForm();
    },
    onError: (err: any) => {
      if (!err.response) {
        setError('Connection error: Unable to reach the server. Please check your internet connection and try again.');
        return;
      }

      const data = err.response?.data;
      console.error('[RecordPaymentModal] Error response:', data);

      const flatten = (val: any): string => {
        if (typeof val === 'string') return val;
        if (Array.isArray(val)) return val.map(flatten).join(', ');
        if (val && typeof val === 'object') {
          return Object.entries(val)
            .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${flatten(v)}`)
            .join(' • ');
        }
        return String(val);
      };

      let msg = 'Payment could not be recorded. Please try again.';
      if (typeof data === 'string') {
        msg = data;
      } else if (data) {
        const detail = data.detail ?? data.error ?? data;
        if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
          const lines = Object.entries(detail)
            .map(([field, msgs]) => `${field.replace(/_/g, ' ')}: ${flatten(msgs)}`)
            .join(' • ');
          msg = lines || flatten(data);
        } else {
          msg = flatten(detail);
        }
      }
      setError(msg || 'Payment could not be recorded. Please try again.');
    },
  });

  const resetForm = () => {
    setAmount('');
    setReference('');
    setPayerName('');
    setNotes('');
    setMethod('cash');
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const numAmount = amount === '' ? 0 : Number(amount);

    let resolvedId = activeRecordId;

    // Auto-resolve if user typed student code directly and hit submit
    if (!resolvedId && !initialStudentName && studentSearch.trim()) {
      const q = studentSearch.trim().toLowerCase();
      const match =
        searchResults.find(
          (r: any) =>
            (r.student_id_code && r.student_id_code.toLowerCase() === q) ||
            (r.student_name && r.student_name.toLowerCase() === q)
        ) || (searchResults.length === 1 ? searchResults[0] : null);

      if (match) {
        resolvedId = match.id;
        setSelectedRecord(match);
      }
    }

    // Guard 0: Student must be selected or resolved
    if (!resolvedId && !initialStudentName) {
      setError('Please search and select a student with an active fee account from the dropdown list.');
      return;
    }

    // Guard 1: Empty / zero amount
    if (numAmount <= 0) {
      setError(`Please enter a payment amount greater than ${currency} 0. The amount field cannot be empty or zero.`);
      return;
    }

    recordPayment(resolvedId);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Record Fee Payment"
      description="Record cash, bank, or cheque payment and dispatch instant WhatsApp receipt"
      maxWidth="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
            {error}
          </div>
        )}

        {/* Student Header Summary or Live Searchable Selector */}
        {activeStudentName ? (
          <div className="p-3.5 bg-slate-800 rounded-xl border border-slate-700 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <User className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs font-bold text-white">{activeStudentName}</p>
                <p className="text-[10px] font-mono text-emerald-400">
                  {activeStudentCode} {activeClassName ? `• ${activeClassName}` : ''}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-[10px] text-slate-400 uppercase tracking-wider">Outstanding Balance</p>
                <p className={`text-xs font-bold ${activeBalance <= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {activeBalance < 0
                    ? `Credit: ${currency} ${Math.abs(activeBalance).toLocaleString()}`
                    : activeBalance === 0
                    ? 'Fully Cleared'
                    : `${currency} ${activeBalance.toLocaleString()}`}
                </p>
              </div>
              {!initialStudentName && (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedRecord(null);
                    setStudentSearch('');
                    setDropdownOpen(true);
                  }}
                  className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700/50"
                  title="Select different student"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="relative" ref={searchContainerRef}>
            <TextInput
              label="Select Student (Search by Name or Code)"
              placeholder="e.g. Akello Grace or SCH-2026-0001"
              value={studentSearch}
              onChange={(e) => {
                setStudentSearch(e.target.value);
                setDropdownOpen(true);
              }}
              onFocus={() => setDropdownOpen(true)}
              leftIcon={
                isSearching ? (
                  <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
                ) : (
                  <Search className="w-4 h-4 text-slate-400" />
                )
              }
              required
            />

            {dropdownOpen && (
              <div className="absolute left-0 right-0 top-full mt-1 max-h-56 overflow-y-auto bg-slate-800 border border-slate-700 rounded-xl shadow-2xl z-50 divide-y divide-slate-700/50">
                {isSearching && searchResults.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                    Searching records...
                  </div>
                ) : searchResults.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-400">
                    {studentSearch.trim()
                      ? `No student found matching "${studentSearch}"`
                      : 'Type a name or student ID code to search'}
                  </div>
                ) : (
                  searchResults.slice(0, 10).map((fr: any) => {
                    const sName =
                      fr.student_name ||
                      (typeof fr.student === 'object'
                        ? `${fr.student.first_name} ${fr.student.last_name}`
                        : '');
                    const sCode = fr.student_id_code || fr.student?.student_id || '';
                    const sCls = fr.class_name || fr.student?.current_class?.name || '';
                    const sBal = Number(fr.balance || 0);

                    return (
                      <button
                        key={fr.id}
                        type="button"
                        onClick={() => {
                          setSelectedRecord(fr);
                          setStudentSearch(sName);
                          setDropdownOpen(false);
                          if (error) setError(null);
                        }}
                        className="w-full text-left p-3 hover:bg-slate-700/60 transition-colors flex items-center justify-between text-xs"
                      >
                        <div>
                          <p className="font-semibold text-white">{sName}</p>
                          <p className="text-[10px] text-slate-400 font-mono">
                            {sCode} {sCls ? `• ${sCls}` : ''}
                          </p>
                        </div>
                        <div className="text-right">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              fr.is_student_fallback
                                ? 'bg-indigo-500/10 text-indigo-400'
                                : sBal <= 0
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : 'bg-rose-500/10 text-rose-400'
                            }`}
                          >
                            {fr.is_student_fallback
                              ? 'NEW ACCOUNT'
                              : sBal <= 0
                              ? 'CLEARED'
                              : `BAL: ${currency} ${sBal.toLocaleString()}`}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}

        {/* Live credit preview when overpayment is about to be made */}
        {activeStudentName && typeof amount === 'number' && amount > 0 && activeBalance > 0 && amount > activeBalance && (
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs space-y-1">
            <p className="font-semibold">Overpayment — Credit will be applied</p>
            <p>
              {currency} {amount.toLocaleString()} paid on a {currency} {activeBalance.toLocaleString()} balance.
              A credit of{' '}
              <span className="font-bold text-emerald-400">
                {currency} {(amount - activeBalance).toLocaleString()}
              </span>{' '}
              will be recorded on the student ledger.
            </p>
          </div>
        )}

        {/* Payment on already-cleared account */}
        {activeStudentName && typeof amount === 'number' && amount > 0 && activeBalance <= 0 && (
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs space-y-1">
            <p className="font-semibold">Account already cleared — Additional credit will be applied</p>
            <p>
              This account has{' '}
              {activeBalance < 0
                ? `an existing credit of ${currency} ${Math.abs(activeBalance).toLocaleString()}.`
                : 'a zero balance.'}{' '}
              Posting {currency} {amount.toLocaleString()} will add to the student credit ledger.
            </p>
          </div>
        )}

        {/* Large payment threshold warning */}
        {typeof amount === 'number' && amount > 500000 && (
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <span>
              <strong>Director Approval Required:</strong> Payments exceeding {currency} 500,000 are placed in the Approval Queue and require Director authorization before being credited to the student's balance.
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <CurrencyInput
            label={`Payment Amount (${currency})`}
            value={amount}
            onChange={(val) => {
              setAmount(val);
              if (error) setError(null);
            }}
            currencyPrefix={currency}
            helperText={
              typeof amount === 'number' && amount > 0
                ? activeBalance > 0 && amount > activeBalance
                  ? `Credit of ${currency} ${(amount - activeBalance).toLocaleString()} will be applied to ledger`
                  : `${currency} ${amount.toLocaleString()}`
                : `Enter amount in ${currency}`
            }
          />
          <Select
            label="Payment Method"
            options={paymentMethods}
            value={method}
            onChange={(e) => setMethod(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <TextInput
            label="Reference / Receipt No."
            placeholder="e.g. CSH-849201 or Bank Ref"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
          <TextInput
            label="Payer Full Name"
            placeholder="e.g. Guardian Name / Depositor"
            value={payerName}
            onChange={(e) => setPayerName(e.target.value)}
          />
        </div>

        {/* Payment Notes / Remarks (Optional) */}
        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-slate-300">
            Notes / Remarks <span className="text-slate-500 font-normal">(Optional)</span>
          </label>
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. Term 1 fee instalment, cheque #10294, or special payment remarks"
            className="w-full px-3.5 py-2.5 bg-slate-900/60 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500 transition-all resize-none"
          />
        </div>

        {/* WhatsApp Receipt Toggle */}
        <label className="flex items-center gap-3 p-3 bg-slate-850 border border-slate-700/60 rounded-xl cursor-pointer hover:bg-slate-800 transition-colors">
          <input
            type="checkbox"
            checked={sendWhatsAppReceipt}
            onChange={(e) => setSendWhatsAppReceipt(e.target.checked)}
            className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-emerald-500 focus:ring-emerald-500"
          />
          <div className="flex items-center gap-2 text-xs">
            <MessageSquare className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="text-slate-200 font-medium">Send Instant WhatsApp Receipt to Primary Guardian</span>
          </div>
        </label>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            isLoading={isPending}
            leftIcon={<CreditCard className="w-4 h-4" />}
          >
            Save Payment & Send Receipt
          </Button>
        </div>
      </form>
    </Modal>
  );
};
