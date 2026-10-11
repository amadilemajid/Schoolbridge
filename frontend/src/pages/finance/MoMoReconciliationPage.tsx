import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { TextInput } from '../../components/ui/TextInput';
import {
  CheckCircle2, Search, ArrowLeft, Clock, AlertTriangle,
  Ban, History, RefreshCw, User, FileText, Smartphone,
  ChevronRight, Zap, CheckCheck, Info, X, Upload, Building2,
  Phone, Calendar, Sparkles,
} from 'lucide-react';
import { Link } from 'react-router-dom';

// ─── Format Detector Helper ───────────────────────────────────────────────────

interface DetectedProfileInfo {
  key: 'centenary' | 'stanbic' | 'mtn_momo' | 'unknown';
  name: string;
  matchedHeaders: string[];
}

function detectCsvProfile(headers: string[]): DetectedProfileInfo {
  const clean = headers.map(h => h.trim().toLowerCase().replace(/^["']|["']$/g, ''));

  // 1. Check MoMo first (most distinctive headers)
  const momoKeywords = ['external transaction id', 'financial transaction id', 'msisdn', 'transaction id'];
  const momoMatches = clean.filter(h => momoKeywords.includes(h));
  if (momoMatches.length > 0 || (clean.includes('from') && clean.includes('amount'))) {
    return {
      key: 'mtn_momo',
      name: 'MTN Mobile Money / Airtel Money',
      matchedHeaders: momoMatches.length > 0 ? momoMatches : ['from', 'amount'],
    };
  }

  // 2. Check Centenary Bank (particulars, cheque no, document no)
  const centKeywords = ['particulars', 'cheque no', 'document no'];
  const centMatches = clean.filter(h => centKeywords.includes(h));
  if (centMatches.length > 0) {
    return {
      key: 'centenary',
      name: 'Centenary Bank Uganda',
      matchedHeaders: centMatches,
    };
  }

  // 3. Check Stanbic Bank (posting date, credit amount, transaction reference, narrative)
  const stanbicKeywords = ['posting date', 'credit amount', 'transaction reference', 'narrative'];
  const stanbicMatches = clean.filter(h => stanbicKeywords.includes(h));
  if (stanbicMatches.length > 0) {
    return {
      key: 'stanbic',
      name: 'Stanbic Bank Uganda',
      matchedHeaders: stanbicMatches,
    };
  }

  return {
    key: 'unknown',
    name: 'Generic Bank / CSV Format',
    matchedHeaders: [],
  };
}

// ─── Types ─────────────────────────────────────────────────────────────────────

interface SuggestedStudent {
  student_id: string;
  name: string;
  phone?: string;
  score?: number;
}

interface UnmatchedTransaction {
  id: string;
  phone: string;
  amount: number;
  provider: string;
  momo_reference?: string;
  transaction_reference?: string;
  narration?: string | null;
  received_at: string;
  status: 'pending' | 'matched' | 'ignored';
  ignore_reason?: string;
  suggested_students?: SuggestedStudent[] | null;
  alert_24hr_sent: boolean;
  alert_48hr_sent: boolean;
  matched_at?: string | null;
  matched_by_name?: string | null;
  matched_student_name?: string | null;
  matched_student_id_code?: string | null;
  matched_student_class?: string | null;
  receipt_number?: string | null;
  academic_term?: string | null;
}

interface StudentSearchResult {
  id: string;
  student_id: string;
  first_name: string;
  last_name: string;
  current_class?: { name: string };
}

interface FeeRecord {
  id: string;
  term_label?: string;
  academic_year?: string;
  total_amount: number;
  amount_paid: number;
  balance: number;
  is_fully_paid: boolean;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function ageDays(dateStr: string): number {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86_400_000);
}

function AgeBadge({ received_at, alert_48hr_sent }: {
  received_at: string;
  alert_48hr_sent: boolean;
}) {
  const days = ageDays(received_at);
  if (days === 0) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
      <Clock className="w-2.5 h-2.5" /> Today
    </span>
  );
  if (days <= 1) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30">
      <Clock className="w-2.5 h-2.5" /> 1 day
    </span>
  );
  if (days <= 3) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
      <AlertTriangle className="w-2.5 h-2.5" /> {days}d
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 animate-pulse">
      <AlertTriangle className="w-2.5 h-2.5" /> {days}d overdue{alert_48hr_sent ? ' • Escalated' : ''}
    </span>
  );
}

function ProviderBadge({ provider }: { provider: string }) {
  const p = (provider || '').toLowerCase();
  if (p.includes('centenary')) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold border bg-blue-600/15 text-blue-300 border-blue-500/30">
        <Building2 className="w-3 h-3" />
        Centenary Bank
      </span>
    );
  }
  if (p.includes('stanbic')) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold border bg-cyan-600/15 text-cyan-300 border-cyan-500/30">
        <Building2 className="w-3 h-3" />
        Stanbic Bank
      </span>
    );
  }
  const isMTN = p.includes('mtn');
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold border ${
      isMTN
        ? 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30'
        : 'bg-red-500/15 text-red-300 border-red-500/30'
    }`}>
      <Smartphone className="w-3 h-3" />
      {isMTN ? 'MTN MoMo' : 'Airtel Money'}
    </span>
  );
}

// ─── TxRow component ───────────────────────────────────────────────────────────

function TxRow({ tx, isPending, onMatch, onIgnore }: {
  tx: UnmatchedTransaction;
  isPending: boolean;
  onMatch: (tx: UnmatchedTransaction) => void;
  onIgnore: (tx: UnmatchedTransaction) => void;
}) {
  const days = ageDays(tx.received_at);
  const isUrgent = days >= 3 && isPending;

  return (
    <div className={`rounded-xl border p-4 transition-all ${
      tx.status === 'matched'
        ? 'bg-emerald-950/20 border-emerald-500/20'
        : tx.status === 'ignored'
        ? 'bg-slate-800/40 border-slate-700/40 opacity-70'
        : isUrgent
        ? 'bg-rose-950/20 border-rose-500/20 shadow-[0_0_16px_rgba(239,68,68,0.06)]'
        : 'bg-slate-800/60 border-slate-700/40 hover:border-slate-600'
    }`}>
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`p-2.5 rounded-xl border shrink-0 mt-0.5 ${
            tx.status === 'matched'
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
              : tx.status === 'ignored'
              ? 'bg-slate-700/50 border-slate-600/30 text-slate-500'
              : isUrgent
              ? 'bg-rose-500/10 border-rose-500/20 text-rose-400'
              : 'bg-amber-500/10 border-amber-500/20 text-amber-400'
          }`}>
            {tx.status === 'matched' ? <CheckCircle2 className="w-4 h-4" />
              : tx.status === 'ignored' ? <Ban className="w-4 h-4" />
              : <Clock className="w-4 h-4" />}
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <ProviderBadge provider={tx.provider} />
              <span className="inline-flex items-center gap-1.5 font-mono font-bold text-xs sm:text-sm text-slate-200 bg-slate-900/60 px-2 py-0.5 rounded-lg border border-slate-700/60">
                <Phone className="w-3 h-3 text-slate-400" />
                <span className="text-slate-400 font-sans text-xs font-normal">Payer:</span>
                {tx.phone && tx.phone !== 'N/A' ? tx.phone : <span className="font-sans font-normal text-xs text-slate-400 italic">Direct Deposit / Ref</span>}
              </span>
              {isPending && (
                <AgeBadge received_at={tx.received_at} alert_48hr_sent={tx.alert_48hr_sent} />
              )}
              {isPending && tx.suggested_students && tx.suggested_students.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                  <Zap className="w-2.5 h-2.5" />
                  {tx.suggested_students.length} AI suggestion{tx.suggested_students.length > 1 ? 's' : ''}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
              <span>Amount: <span className="text-emerald-400 font-bold font-mono">UGX {Number(tx.amount).toLocaleString()}</span></span>
              {(tx.momo_reference || tx.transaction_reference) && (
                <span>Ref: <span className="font-mono text-slate-300">{tx.momo_reference || tx.transaction_reference}</span></span>
              )}
              <span className="inline-flex items-center gap-1 text-slate-400">
                <Calendar className="w-3 h-3 text-slate-500" />
                <span>Date:</span>
                <span className="text-slate-300">{new Date(tx.received_at).toLocaleString()}</span>
              </span>
            </div>

            {tx.narration && (
              <p className="text-[11px] text-amber-300/90 italic mt-1.5 flex items-center gap-1.5 bg-amber-500/5 px-2 py-0.5 rounded-md border border-amber-500/10 w-fit">
                <FileText className="w-3 h-3 text-amber-400 shrink-0" />
                <span className="not-italic font-semibold text-amber-400/90">Payer Note:</span>
                &ldquo;{tx.narration}&rdquo;
              </p>
            )}

            {tx.status === 'matched' && (
              <div className="mt-2.5 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  <div>
                    <span className="font-semibold text-white">
                      Credited to {tx.matched_student_name || 'Student'}
                    </span>
                    {tx.matched_student_id_code && (
                      <span className="font-mono text-[11px] text-slate-300 ml-1.5 bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-700">
                        {tx.matched_student_id_code}
                      </span>
                    )}
                    {tx.matched_student_class && (
                      <span className="text-slate-400 text-xs ml-1.5">
                        ({tx.matched_student_class})
                      </span>
                    )}
                    {tx.academic_term && (
                      <span className="text-emerald-400/80 text-xs ml-1.5 font-medium">
                        &middot; {tx.academic_term}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-slate-400 text-[11px]">
                  {tx.receipt_number && (
                    <span>Receipt: <span className="font-mono text-slate-300">{tx.receipt_number}</span></span>
                  )}
                  {tx.matched_by_name && <span>&middot; by <strong className="text-slate-300">{tx.matched_by_name}</strong></span>}
                  {tx.matched_at && <span>&middot; {new Date(tx.matched_at).toLocaleDateString()}</span>}
                </div>
              </div>
            )}
            {tx.status === 'ignored' && tx.ignore_reason && (
              <div className="mt-2.5 p-2 rounded-lg bg-slate-800/60 border border-slate-700 text-xs flex flex-wrap items-center justify-between gap-2 text-slate-400">
                <p className="flex items-center gap-1.5 text-slate-400">
                  <Ban className="w-3.5 h-3.5 text-slate-500" />
                  <span>Ignored: <strong className="text-slate-300 italic">{tx.ignore_reason}</strong></span>
                </p>
                {tx.matched_by_name && (
                  <span className="text-[11px] text-slate-500">
                    by {tx.matched_by_name} &middot; {tx.matched_at ? new Date(tx.matched_at).toLocaleDateString() : ''}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {isPending && (
          <div className="flex items-center gap-2 shrink-0 ml-auto">
            <Button
              variant="ghost" size="sm"
              className="text-xs text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-500/40"
              leftIcon={<Ban className="w-3.5 h-3.5" />}
              onClick={() => onIgnore(tx)}
            >
              Ignore
            </Button>
            <Button
              variant="primary" size="sm"
              className={`text-xs ${isUrgent ? 'bg-rose-600 hover:bg-rose-500' : 'bg-emerald-600 hover:bg-emerald-500'}`}
              leftIcon={<User className="w-3.5 h-3.5" />}
              onClick={() => onMatch(tx)}
            >
              {tx.suggested_students && tx.suggested_students.length > 0 ? 'Match ✦' : 'Match Student'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────────

export const MoMoReconciliationPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'pending' | 'resolved'>('pending');
  const [search, setSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // Match modal
  const [selectedTx, setSelectedTx] = useState<UnmatchedTransaction | null>(null);
  const [studentQuery, setStudentQuery] = useState('');
  const [selectedStudent, setSelectedStudent] = useState<StudentSearchResult | null>(null);
  const [selectedFeeRecordId, setSelectedFeeRecordId] = useState('');
  const [matchError, setMatchError] = useState<string | null>(null);

  // Ignore modal
  const [ignoringTx, setIgnoringTx] = useState<UnmatchedTransaction | null>(null);
  const [ignoreReason, setIgnoreReason] = useState('');
  const [ignoreError, setIgnoreError] = useState<string | null>(null);

  // Bank Statement Import modal
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [statementFile, setStatementFile] = useState<File | null>(null);
  const [statementFormat, setStatementFormat] = useState('auto');
  const [detectedProfile, setDetectedProfile] = useState<DetectedProfileInfo | null>(null);
  const [importFeedback, setImportFeedback] = useState<{ type: 'success' | 'error' | 'warning'; message: string; formatName?: string } | null>(null);

  const handleStatementFileSelect = (f: File | null) => {
    setStatementFile(f);
    setDetectedProfile(null);
    setImportFeedback(null);
    if (!f) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) || '';
      const allLines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);

      // Scan through the first 10 non-empty lines to find the real header row.
      // Some bank exports (e.g. Centenary) have a title/metadata row before the actual CSV headers.
      // A "real" header row is identified by having ≥3 delimiter-separated tokens.
      let detectedHeaders: string[] = [];
      for (const line of allLines.slice(0, 10)) {
        const delimiter = (line.includes(';') && !line.includes(','))
          ? ';'
          : (line.includes('\t') && !line.includes(',')) ? '\t' : ',';
        const parts = line.split(delimiter).map(h => h.trim().replace(/^["']|["']$/g, ''));
        if (parts.length >= 3) {
          // Prefer this as the header row if it has recognisable keyword headers
          const lowerParts = parts.map(p => p.toLowerCase());
          const hasHeaderKeywords = lowerParts.some(p =>
            ['date', 'amount', 'reference', 'narration', 'particulars', 'description',
             'credit', 'debit', 'balance', 'narrative', 'from', 'cheque', 'posting'].some(kw => p.includes(kw))
          );
          if (hasHeaderKeywords) {
            detectedHeaders = parts;
            break;
          }
          // Fallback: take first line with ≥3 fields even without keywords
          if (!detectedHeaders.length) {
            detectedHeaders = parts;
          }
        }
      }

      if (detectedHeaders.length > 0) {
        const detected = detectCsvProfile(detectedHeaders);
        setDetectedProfile(detected);
      }
    };
    reader.readAsText(f.slice(0, 8192));
  };

  // ── Queries ────────────────────────────────────────────────────────────────

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['momo-reconciliation', activeTab, search, currentPage, providerFilter],
    queryFn: async () => {
      const statusMap: Record<string, string> = { pending: 'pending', resolved: 'resolved' };
      const params: Record<string, any> = {
        page: currentPage, page_size: pageSize,
        status: statusMap[activeTab],
      };
      if (search) params.search = search;
      if (providerFilter) params.provider = providerFilter;
      const res = await apiClient.get('/payments/reconciliation/', { params });
      return res.data;
    },
  });

  const { data: pendingCount = 0 } = useQuery({
    queryKey: ['momo-pending-count'],
    queryFn: async () => {
      const res = await apiClient.get('/payments/reconciliation/', { params: { status: 'pending', page_size: 1 } });
      return res.data?.count ?? 0;
    },
    refetchInterval: 30_000,
  });

  const { data: studentResultsData } = useQuery({
    queryKey: ['student-search-match', studentQuery],
    queryFn: async () => {
      if (studentQuery.length < 2) return [];
      const res = await apiClient.get('/students/', { params: { search: studentQuery, page_size: 6 } });
      return (res.data?.results || res.data || []) as StudentSearchResult[];
    },
    enabled: studentQuery.length >= 2,
  });
  const studentResults: StudentSearchResult[] = studentResultsData || [];

  const { data: feeRecordsData, isLoading: loadingFeeRecords } = useQuery({
    queryKey: ['student-fee-records-recon', selectedStudent?.id],
    queryFn: async () => {
      const res = await apiClient.get('/payments/fee-records/', {
        params: { student_id: selectedStudent!.id, page_size: 10 },
      });
      const list: FeeRecord[] = res.data?.results || res.data || [];
      return list.filter(r => !r.is_fully_paid);
    },
    enabled: !!selectedStudent,
  });
  const feeRecords: FeeRecord[] = feeRecordsData || [];

  React.useEffect(() => {
    if (feeRecords.length > 0 && !selectedFeeRecordId) {
      setSelectedFeeRecordId(feeRecords[0].id);
    }
  }, [feeRecords.length]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const { mutate: matchTransaction, isPending: matching } = useMutation({
    mutationFn: async () => {
      if (!selectedTx || !selectedStudent) return;
      const res = await apiClient.post(`/payments/reconciliation/${selectedTx.id}/match/`, {
        student_id: selectedStudent.id,
        ...(selectedFeeRecordId ? { fee_record_id: selectedFeeRecordId } : {}),
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['momo-reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['momo-pending-count'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      setSelectedTx(null); setSelectedStudent(null); setStudentQuery(''); setSelectedFeeRecordId(''); setMatchError(null);
    },
    onError: (err: any) => {
      const raw = err.response?.data;
      setMatchError((typeof raw?.error === 'string' ? raw.error : null) || (typeof raw?.detail === 'string' ? raw.detail : null) || 'Failed to match transaction.');
    },
  });

  const { mutate: ignoreTransaction, isPending: ignoring } = useMutation({
    mutationFn: async () => {
      if (!ignoringTx || ignoreReason.trim().length < 5) return;
      const res = await apiClient.post(`/payments/reconciliation/${ignoringTx.id}/ignore/`, { reason: ignoreReason.trim() });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['momo-reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['momo-pending-count'] });
      setIgnoringTx(null); setIgnoreReason(''); setIgnoreError(null);
    },
    onError: (err: any) => {
      const raw = err.response?.data;
      setIgnoreError((typeof raw?.error === 'string' ? raw.error : null) || 'Failed to ignore transaction.');
    },
  });

  const { mutate: importStatement, isPending: importing } = useMutation({
    mutationFn: async () => {
      if (!statementFile) throw new Error('Please select a CSV file to upload.');
      const formData = new FormData();
      formData.append('file', statementFile);
      formData.append('format', statementFormat);
      const res = await apiClient.post('/payments/reconciliation/import-statement/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    },
    onSuccess: (resData) => {
      queryClient.invalidateQueries({ queryKey: ['momo-reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['momo-pending-count'] });
      const formatName = resData.format_name || resData.detected_format || 'Bank Statement';
      // Show amber warning when all rows were duplicates (nothing new was imported)
      const feedbackType = resData.already_imported ? 'warning' : 'success';
      setImportFeedback({
        type: feedbackType,
        message: resData.message || `Imported ${resData.imported} transactions successfully.`,
        formatName,
      });
      setStatementFile(null);
      setDetectedProfile(null);
      // Auto-switch to Pending Queue so user immediately sees newly imported transactions
      setActiveTab('pending');
      setCurrentPage(1);
      // Auto-close only on true success; keep warning visible so user can read it
      if (feedbackType === 'success') {
        setTimeout(() => {
          setImportModalOpen(false);
          setImportFeedback(null);
        }, 3500);
      }
    },
    onError: (err: any) => {
      const raw = err.response?.data;
      // Handle both string and array error shapes from DRF
      const detail = typeof raw?.detail === 'string'
        ? raw.detail
        : Array.isArray(raw?.detail) ? raw.detail[0] : null;
      const fileErr = typeof raw?.file === 'string'
        ? raw.file
        : Array.isArray(raw?.file) ? raw.file[0] : null;
      setImportFeedback({
        type: 'error',
        message: detail || fileErr || 'Failed to process bank statement CSV. Please check the file and try again.',
      });
    },
  });

  const { mutate: autoMatchSuggestions, isPending: autoMatching } = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/payments/reconciliation/auto-match-suggestions/');
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['momo-reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['momo-pending-count'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      setActiveTab('resolved');
      setCurrentPage(1);
    },
  });

  // ── Derived ────────────────────────────────────────────────────────────────

  const txList: UnmatchedTransaction[] = data?.results || [];
  const totalCount: number = data?.count || 0;
  const totalPages = Math.ceil(totalCount / pageSize);
  const selectedFeeRecord = useMemo(() => feeRecords.find(r => r.id === selectedFeeRecordId), [feeRecords, selectedFeeRecordId]);

  const confidentCount = useMemo(() => {
    if (activeTab !== 'pending') return 0;
    return txList.filter(t => t.suggested_students && t.suggested_students.length > 0 && (t.suggested_students[0].score || 0) >= 90).length;
  }, [txList, activeTab]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to="/finance" className="text-slate-400 hover:text-white transition-colors"><ArrowLeft className="w-4 h-4" /></Link>
            <h1 className="text-2xl font-bold text-white tracking-tight">MoMo & Bank Reconciliation Queue</h1>
            {pendingCount > 0 && (
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30 animate-pulse">
                {pendingCount} pending
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 ml-6">
            Match unmatched Mobile Money & Bank payments to student accounts · mark non-school payments as ignored
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Upload className="w-3.5 h-3.5" />}
            onClick={() => { setImportModalOpen(true); setImportFeedback(null); setStatementFile(null); setDetectedProfile(null); }}
            className="text-slate-200"
          >
            Import Statement
          </Button>
          <Button variant="ghost" size="sm" leftIcon={<RefreshCw className="w-3.5 h-3.5" />} onClick={() => refetch()} className="text-slate-400 hover:text-white">
            Refresh
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-800/60 rounded-xl border border-slate-700/50 w-fit">
        {(['pending', 'resolved'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setCurrentPage(1); }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              activeTab === tab ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/40' : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab === 'pending' ? <Clock className="w-3.5 h-3.5" /> : <History className="w-3.5 h-3.5" />}
            {tab === 'pending' ? 'Pending Queue' : 'Resolved History'}
            {tab === 'pending' && pendingCount > 0 && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-white/20">{pendingCount}</span>
            )}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setCurrentPage(1); }}
            placeholder="Search phone number, student ref or transaction reference…"
            className="w-full pl-9 pr-3 py-2.5 bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 placeholder-slate-500"
          />
        </div>
        <select
          value={providerFilter}
          onChange={e => { setProviderFilter(e.target.value); setCurrentPage(1); }}
          className="bg-slate-800 border border-slate-700 text-slate-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">All Providers & Banks</option>
          <option value="mtn">MTN Mobile Money</option>
          <option value="airtel">Airtel Money</option>
          <option value="centenary">Centenary Bank</option>
          <option value="stanbic">Stanbic Bank</option>
        </select>
        {(search || providerFilter) && (
          <button onClick={() => { setSearch(''); setProviderFilter(''); setCurrentPage(1); }} className="px-3 py-2.5 text-xs text-slate-400 hover:text-white border border-slate-700 rounded-xl flex items-center gap-1">
            <X className="w-3 h-3" /> Clear
          </button>
        )}
      </div>

      {/* Auto-Match Suggestions Banner (Pending Queue) */}
      {activeTab === 'pending' && confidentCount > 0 && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/25">
          <div className="flex items-center gap-2.5 text-xs text-indigo-300">
            <Zap className="w-4 h-4 text-indigo-400 shrink-0" />
            <span>
              <strong>{confidentCount} transaction{confidentCount > 1 ? 's have' : ' has'} high-confidence student matches (≥90%).</strong>
              <span className="text-slate-400 ml-1">You can automatically match and credit them to student fee records in one click.</span>
            </span>
          </div>
          <Button
            size="sm"
            variant="primary"
            isLoading={autoMatching}
            onClick={() => autoMatchSuggestions()}
            className="bg-indigo-600 hover:bg-indigo-500 text-white shrink-0 shadow-sm"
            leftIcon={<Zap className="w-3.5 h-3.5" />}
          >
            Auto-Match {confidentCount} & Resolve
          </Button>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="h-20 rounded-xl bg-slate-800/50 animate-pulse" />)}</div>
      ) : txList.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-4">
            <CheckCheck className="w-7 h-7 text-emerald-400" />
          </div>
          <p className="text-lg font-semibold text-white">{activeTab === 'pending' ? 'Pending Queue is empty!' : 'No resolved items found'}</p>
          <p className="text-sm text-slate-400 mt-1 max-w-md">
            {activeTab === 'pending'
              ? 'All imported payments have been matched to student records or marked ignored.'
              : 'Transactions from imported bank statements and MoMo initially land in the Pending Queue. Once you click "Match Student" or "Ignore", their resolved details will appear here.'}
          </p>
          {activeTab === 'resolved' && pendingCount > 0 && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => { setActiveTab('pending'); setCurrentPage(1); }}
              leftIcon={<Clock className="w-3.5 h-3.5" />}
              className="mt-4 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
            >
              View Pending Queue ({pendingCount})
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2.5">
          {txList.map(tx => (
            <TxRow key={tx.id} tx={tx} isPending={activeTab === 'pending'} onMatch={setSelectedTx} onIgnore={t => { setIgnoringTx(t); setIgnoreReason(''); setIgnoreError(null); }} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-slate-400">{((currentPage - 1) * pageSize) + 1}–{Math.min(currentPage * pageSize, totalCount)} of {totalCount}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>Prev</Button>
            <span className="px-3 py-1.5 text-xs text-slate-300 bg-slate-800 rounded-lg border border-slate-700">{currentPage} / {totalPages}</span>
            <Button size="sm" variant="ghost" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* ── Match Modal ───────────────────────────────────────────────────────── */}
      {selectedTx && (
        <Modal isOpen onClose={() => { setSelectedTx(null); setMatchError(null); }} title="Manual MoMo Transaction Match" description="Link this payment to a student account and select the term to credit" maxWidth="lg">
          <div className="space-y-5">
            {matchError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />{matchError}
              </div>
            )}

            {/* Transaction card */}
            <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700 space-y-3">
              <div className="flex items-center justify-between">
                <ProviderBadge provider={selectedTx.provider} />
                <AgeBadge received_at={selectedTx.received_at} alert_48hr_sent={selectedTx.alert_48hr_sent} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Payer Phone</p><p className="font-mono font-bold text-sm text-white">{selectedTx.phone}</p></div>
                <div><p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Amount</p><p className="font-bold text-emerald-400 text-lg">UGX {Number(selectedTx.amount).toLocaleString()}</p></div>
                <div><p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Reference</p><p className="font-mono text-xs text-slate-300">{selectedTx.momo_reference || '—'}</p></div>
                <div><p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Received</p><p className="text-xs text-slate-300">{new Date(selectedTx.received_at).toLocaleString()}</p></div>
              </div>
              {selectedTx.narration && (
                <div className="pt-2 border-t border-slate-700/50">
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5 flex items-center gap-1"><FileText className="w-3 h-3" />Payer Note</p>
                  <p className="text-xs text-amber-300 italic">&ldquo;{selectedTx.narration}&rdquo;</p>
                </div>
              )}
            </div>

            {/* AI Suggestions */}
            {selectedTx.suggested_students && selectedTx.suggested_students.length > 0 && (
              <div className="p-3 bg-indigo-500/5 border border-indigo-500/20 rounded-xl">
                <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5" /> AI Suggestions &mdash; Click to instantly select
                </p>
                <div className="space-y-1.5">
                  {selectedTx.suggested_students.map((s, i) => (
                    <button key={i}
                      onClick={async () => {
                        setStudentQuery(s.name);
                        setSelectedStudent(null);
                        setSelectedFeeRecordId('');
                        try {
                          // Fetch the full student object by ID so it can be pre-selected
                          const res = await apiClient.get(`/students/${s.student_id}/`);
                          const st = res.data;
                          setSelectedStudent(st);
                          setStudentQuery(`${st.first_name} ${st.last_name}`);
                        } catch {
                          // Fallback: trigger search by name so the dropdown appears
                          setStudentQuery(s.name);
                        }
                      }}
                      className="w-full flex items-center justify-between p-2 rounded-lg bg-slate-800 hover:bg-indigo-900/30 border border-slate-700 hover:border-indigo-500/40 transition-colors text-xs group"
                    >
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400 text-[10px] font-bold shrink-0">{i + 1}</div>
                        <div className="text-left">
                          <p className="font-semibold text-white">{s.name}</p>
                          {s.phone && <p className="text-[10px] text-slate-400 font-mono">{s.phone}</p>}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {s.score != null && <span className="text-[10px] font-bold text-indigo-300 bg-indigo-500/10 px-1.5 py-0.5 rounded">{Math.round(s.score)}% match</span>}
                        <ChevronRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-indigo-400" />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Student search */}
            <div className="space-y-2">
              <TextInput label="Search Student to Credit" placeholder="Type student name or ID number…" value={studentQuery}
                onChange={e => { setStudentQuery(e.target.value); setSelectedStudent(null); setSelectedFeeRecordId(''); }}
                leftIcon={<Search className="w-4 h-4 text-slate-400" />} />
              {studentResults.length > 0 && !selectedStudent && (
                <div className="bg-slate-900 border border-slate-700 rounded-xl overflow-hidden divide-y divide-slate-800">
                  {studentResults.map(st => (
                    <button key={st.id} type="button" onClick={() => { setSelectedStudent(st); setStudentQuery(`${st.first_name} ${st.last_name}`); setSelectedFeeRecordId(''); }}
                      className="w-full text-left p-3 hover:bg-slate-800 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-slate-300 font-bold text-[11px]">{st.first_name[0]}{st.last_name[0]}</div>
                        <div><p className="font-semibold text-white">{st.first_name} {st.last_name}</p><p className="text-[10px] text-slate-400 font-mono">{st.student_id}</p></div>
                      </div>
                      <span className="text-slate-400 text-[11px]">{st.current_class?.name || 'No class'}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Selected student + fee record picker */}
            {selectedStudent && (
              <div className="space-y-3">
                <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold text-sm">{selectedStudent.first_name[0]}{selectedStudent.last_name[0]}</div>
                    <div><p className="text-xs font-bold text-emerald-300">{selectedStudent.first_name} {selectedStudent.last_name}</p><p className="text-[10px] text-slate-400 font-mono">{selectedStudent.student_id}</p></div>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    <button onClick={() => { setSelectedStudent(null); setStudentQuery(''); setSelectedFeeRecordId(''); }} className="text-slate-400 hover:text-white">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {loadingFeeRecords ? (
                  <div className="h-16 rounded-xl bg-slate-800 animate-pulse" />
                ) : feeRecords.length === 0 ? (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl">
                    <p className="text-xs text-amber-300 flex items-center gap-2">
                      <Info className="w-4 h-4 shrink-0" />
                      No outstanding fee records found. Payment may create a credit balance.
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-xs font-semibold text-slate-300 mb-2">Select term to credit ({feeRecords.length} outstanding):</p>
                    <div className="space-y-1.5">
                      {feeRecords.map(fr => (
                        <button key={fr.id} onClick={() => setSelectedFeeRecordId(fr.id)}
                          className={`w-full flex items-center justify-between p-3 rounded-xl border text-xs transition-all ${
                            selectedFeeRecordId === fr.id ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-slate-700 bg-slate-800/60 hover:border-slate-600'
                          }`}>
                          <div className="text-left">
                            <p className="font-semibold text-white">{fr.term_label || fr.academic_year || 'Current Term'}</p>
                            <p className="text-[10px] text-slate-400 mt-0.5">
                              Balance: <span className="text-rose-400 font-bold font-mono">UGX {Number(fr.balance).toLocaleString()}</span>
                              {' · '}Paid: <span className="text-emerald-400 font-mono">UGX {Number(fr.amount_paid).toLocaleString()}</span>
                            </p>
                          </div>
                          {selectedFeeRecordId === fr.id && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
                        </button>
                      ))}
                    </div>

                    {selectedFeeRecord && (
                      <div className="mt-3 p-3 bg-slate-800 border border-slate-700 rounded-xl space-y-1.5 text-xs">
                        <p className="font-semibold text-slate-300">After crediting this payment:</p>
                        <div className="flex justify-between"><span className="text-slate-400">Current balance</span><span className="font-mono text-rose-400">UGX {Number(selectedFeeRecord.balance).toLocaleString()}</span></div>
                        <div className="flex justify-between"><span className="text-slate-400">This payment</span><span className="font-mono text-emerald-400">− UGX {Number(selectedTx.amount).toLocaleString()}</span></div>
                        <div className="flex justify-between pt-1 border-t border-slate-700 font-bold">
                          <span className="text-slate-300">New balance</span>
                          <span className={`font-mono ${Number(selectedFeeRecord.balance) - Number(selectedTx.amount) <= 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                            UGX {Math.max(0, Number(selectedFeeRecord.balance) - Number(selectedTx.amount)).toLocaleString()}
                            {Number(selectedFeeRecord.balance) - Number(selectedTx.amount) < 0 && <span className="ml-1 text-[10px] text-blue-400">(overpaid)</span>}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
              <Button variant="secondary" onClick={() => { setSelectedTx(null); setMatchError(null); }}>Cancel</Button>
              <Button variant="primary" disabled={!selectedStudent} isLoading={matching} onClick={() => matchTransaction()} leftIcon={<CheckCircle2 className="w-4 h-4" />}>
                Confirm & Credit Account
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Ignore Modal ──────────────────────────────────────────────────────── */}
      {ignoringTx && (
        <Modal isOpen onClose={() => setIgnoringTx(null)} title="Ignore This Transaction" description="Mark as non-school payment. No student balance will be affected. This is logged for audit." maxWidth="md">
          <div className="space-y-4">
            {ignoreError && <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">{ignoreError}</div>}

            <div className="p-3 bg-slate-800 rounded-xl border border-slate-700 space-y-1 text-xs">
              <div className="flex justify-between"><span className="text-slate-400">Phone</span><span className="font-mono font-bold text-white">{ignoringTx.phone}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Amount</span><span className="font-bold text-emerald-400">UGX {Number(ignoringTx.amount).toLocaleString()}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Ref</span><span className="font-mono text-slate-300">{ignoringTx.momo_reference || '—'}</span></div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">Reason for ignoring <span className="text-rose-400">*</span></label>
              <textarea value={ignoreReason} onChange={e => setIgnoreReason(e.target.value)} rows={3}
                placeholder="e.g. Wrong number — payment not meant for this school. Parent confirmed via phone."
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none" />
              <p className="text-[10px] text-slate-500 mt-1">Minimum 5 characters. Logged in audit trail.</p>
            </div>

            <div className="flex justify-end gap-3 pt-2 border-t border-slate-800">
              <Button variant="secondary" onClick={() => setIgnoringTx(null)}>Cancel</Button>
              <Button variant="danger" disabled={ignoreReason.trim().length < 5} isLoading={ignoring} onClick={() => ignoreTransaction()} leftIcon={<Ban className="w-4 h-4" />}>
                Mark as Ignored
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Bank Statement Import Modal ────────────────────────────────────────── */}
      {importModalOpen && (
        <Modal
          isOpen
          onClose={() => { if (!importing) setImportModalOpen(false); }}
          title="Import Bank / MoMo Statement"
          description="Upload CSV export from Centenary Bank, Stanbic Bank, or Mobile Money. New fee deposits will be queued for reconciliation."
          maxWidth="md"
        >
          <div className="space-y-4">
            {importFeedback && (() => {
              const isSuccess = importFeedback.type === 'success';
              const isWarning = importFeedback.type === 'warning';
              return (
                <div className={`p-3.5 rounded-xl border text-xs flex items-start gap-2.5 ${
                  isSuccess
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                    : isWarning
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                    : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                }`}>
                  {isSuccess ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
                  ) : isWarning ? (
                    <Info className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
                  )}
                  <div>
                    <p className="font-bold text-sm text-white">
                      {isSuccess
                        ? 'Statement Processed Successfully'
                        : isWarning
                        ? 'Already Imported — No Duplicates Created'
                        : 'Import Failed'}
                    </p>
                    <p className="mt-0.5 text-slate-300 whitespace-pre-line">{importFeedback.message}</p>
                    {importFeedback.formatName && (
                      <p className={`text-[11px] mt-1 font-medium ${isSuccess ? 'text-emerald-400/90' : isWarning ? 'text-amber-400/90' : 'text-rose-400/90'}`}>
                        Detected Profile: <strong>{importFeedback.formatName}</strong>
                      </p>
                    )}
                  </div>
                </div>
              );
            })()}

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Bank / Provider Profile
              </label>
              <select
                value={statementFormat}
                onChange={e => setStatementFormat(e.target.value)}
                disabled={importing}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="auto">
                  {detectedProfile && detectedProfile.key !== 'unknown'
                    ? `Auto-Detect: ${detectedProfile.name} (Recommended)`
                    : 'Auto-Detect Format (Recommended)'}
                </option>
                <option value="centenary">Centenary Bank Uganda (CSV / Excel)</option>
                <option value="stanbic">Stanbic Bank Uganda (CSV)</option>
                <option value="mtn_momo">MTN Mobile Money / Airtel Money</option>
              </select>
              <p className="text-[11px] text-slate-500 mt-1">
                Column headers are automatically mapped to dates, references, narrations, and credit amounts.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Statement File (.csv) <span className="text-rose-400">*</span>
              </label>
              <div
                className="border-2 border-dashed border-slate-700 hover:border-emerald-500/50 rounded-xl p-4 text-center bg-slate-800/40 transition-colors"
                onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('border-emerald-500'); }}
                onDragLeave={(e) => { e.currentTarget.classList.remove('border-emerald-500'); }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.currentTarget.classList.remove('border-emerald-500');
                  const f = e.dataTransfer.files?.[0];
                  if (f) handleStatementFileSelect(f);
                }}
              >
                <input
                  type="file"
                  accept=".csv,text/csv,text/plain"
                  id="statement-csv-input"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) handleStatementFileSelect(f);
                  }}
                  disabled={importing}
                />
                <label htmlFor="statement-csv-input" className="cursor-pointer flex flex-col items-center gap-2">
                  <div className="p-2.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <Upload className="w-5 h-5" />
                  </div>
                  {statementFile ? (
                    <div>
                      <p className="text-xs font-semibold text-white">{statementFile.name}</p>
                      <p className="text-[10px] text-slate-400">{(statementFile.size / 1024).toFixed(1)} KB · Click to change file</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-xs font-medium text-slate-300">Click to choose statement file or drag here</p>
                      <p className="text-[10px] text-slate-500">Supports .csv exports from Centenary, Stanbic, or MoMo portals</p>
                    </div>
                  )}
                </label>
              </div>

              {/* Instant Auto-Detection Feedback Badge */}
              {detectedProfile && detectedProfile.key !== 'unknown' && (
                <div className="mt-2.5 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-start justify-between gap-3 text-xs animate-in fade-in">
                  <div className="flex items-start gap-2.5">
                    <div className="p-1 rounded-lg bg-emerald-500/20 text-emerald-400 mt-0.5 shrink-0">
                      <Sparkles className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="font-bold text-white text-xs flex items-center gap-1.5">
                        Auto-Detected Profile:
                        <span className="text-emerald-300 font-semibold">{detectedProfile.name}</span>
                      </p>
                      {detectedProfile.matchedHeaders.length > 0 && (
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Matched columns: <span className="text-slate-300 font-mono">{detectedProfile.matchedHeaders.join(', ')}</span>
                        </p>
                      )}
                    </div>
                  </div>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shrink-0">
                    <CheckCircle2 className="w-3 h-3" /> Auto-Verified
                  </span>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <Button variant="secondary" onClick={() => setImportModalOpen(false)} disabled={importing}>
                Cancel
              </Button>
              <Button
                variant="primary"
                disabled={!statementFile || importing}
                isLoading={importing}
                onClick={() => importStatement()}
                leftIcon={<Upload className="w-4 h-4" />}
              >
                Upload & Process
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

