import React, { useState, useCallback, useEffect, useRef } from 'react';
import { apiClient } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { StatGroup } from '../../components/dashboard/StatGroup';
import { KpiCard } from '../../components/dashboard/KpiCard';
import {
  FileText,
  Download,
  BarChart3,
  Users,
  GraduationCap,
  Banknote,
  CalendarCheck,
  FileDown,
  Play,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ChevronDown,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────
interface TermOption { id: number | string; name: string; is_current: boolean }
interface ClassOption { id: number; name: string }

interface KpiData {
  students_registered: number;
  uneb_candidates: number;
  reports_generated: number;
  uneb_exports: number;
  fee_reports_shared: number;
  total_expected_fees: number;
  total_collected_fees: number;
  outstanding_fees: number;
  collection_rate: number;
  current_term: { id: number; name: string } | null;
  all_terms: TermOption[];
  all_classes: ClassOption[];
}

interface FeeByClass {
  class: string;
  students: number;
  expected: number;
  collected: number;
  waivers: number;
  outstanding: number;
  collection_rate: number;
}

interface FeeReport {
  term: string;
  term_id: number;
  school: string;
  total_expected: number;
  total_collected: number;
  total_waivers: number;
  outstanding: number;
  collection_rate: number;
  by_class: FeeByClass[];
}

interface DailyRow {
  date: string;
  day_name: string;
  present_count: number;
  absent_count: number;
  excused_count: number;
  total_students: number;
  attendance_rate: number;
}

interface AttendanceReport {
  term: string | null;
  class_name: string;
  date_from: string;
  date_to: string;
  total_students: number;
  overall_rate: number;
  total_present: number;
  total_absent: number;
  daily_breakdown: DailyRow[];
}

type ReportResult = FeeReport | AttendanceReport | any | null;
type ReportType = 'fee_collection' | 'attendance_summary' | 'enrolment' | 'student_roster' | 'defaulter_list' | 'uneb_registration' | 'term_results' | 'result_slips';

// ─────────────────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────────────────
const fmt = (n: number) => new Intl.NumberFormat('en-UG').format(Math.round(n || 0));
const pct = (n: number) => `${(n || 0).toFixed(1)}%`;

function isFeeReport(r: ReportResult): r is FeeReport {
  return !!r && 'by_class' in r;
}
function isAttReport(r: ReportResult): r is AttendanceReport {
  return !!r && 'daily_breakdown' in r;
}

// ─────────────────────────────────────────────────────────
// Static report templates (for quick-export tile grid)
// ─────────────────────────────────────────────────────────
const REPORT_TEMPLATES = [
  {
    id: 'student_roster',
    name: 'Student Roster Report',
    description: 'Full directory with guardian contacts and class assignments',
    category: 'academic' as const,
    formats: ['pdf', 'csv', 'excel'],
  },
  {
    id: 'attendance_summary',
    name: 'Attendance Summary Report',
    description: 'Class-level and student-level attendance statistics with absence patterns',
    category: 'attendance' as const,
    formats: ['pdf', 'excel'],
  },
  {
    id: 'fee_collection',
    name: 'Fee Collection & Outstanding Balances',
    description: 'Bursar revenue summary, individual balances, and per-class breakdown',
    category: 'financial' as const,
    formats: ['pdf', 'excel'],
  },
  {
    id: 'term_results',
    name: 'Term Results & Grade Distribution',
    description: 'Per-class mark sheets, UNEB grade distributions, and pass rates',
    category: 'academic' as const,
    formats: ['pdf', 'excel'],
  },
  {
    id: 'defaulter_list',
    name: 'Fee Defaulters Report',
    description: 'Classified defaulters by escalation level with guardian contact details',
    category: 'financial' as const,
    formats: ['pdf', 'csv'],
  },
  {
    id: 'uneb_registration',
    name: 'UNEB UCE Registration Export',
    description: 'UNEB-compliant student data extract ready for online submission',
    category: 'uneb' as const,
    formats: ['csv', 'excel'],
  },
  {
    id: 'result_slips',
    name: 'Student Result Slips',
    description: 'Individual result slips for each student (A4/A5 PDF batch print)',
    category: 'uneb' as const,
    formats: ['pdf'],
  },
];

const categoryColor: Record<string, string> = {
  academic: 'text-sky-400',
  financial: 'text-emerald-400',
  attendance: 'text-amber-400',
  uneb: 'text-rose-400',
};

const categoryBadge: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
  academic: 'info',
  financial: 'success',
  attendance: 'warning',
  uneb: 'danger',
};

// ─────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────
export const ReportsPage: React.FC = () => {
  // Report Generator Studio state
  const [reportType, setReportType] = useState<ReportType>('fee_collection');
  const [selectedTermId, setSelectedTermId] = useState<string>('current');
  const [selectedClassId, setSelectedClassId] = useState<string>('');
  const [selectedDays, setSelectedDays] = useState<string>('');
  const [generating, setGenerating] = useState(false);
  const [exportingFmt, setExportingFmt] = useState<string | null>(null);
  const [reportResult, setReportResult] = useState<ReportResult>(null);
  const [reportError, setReportError] = useState<string | null>(null);

  // Quick-export tile state
  const [quickExportingId, setQuickExportingId] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState('');

  // ── Live KPI — direct fetch, zero cache, re-runs on every mount ─────────
  const [kpi, setKpi] = useState<KpiData | null>(null);
  const [kpiLoading, setKpiLoading] = useState(true);
  const [kpiLastUpdated, setKpiLastUpdated] = useState<Date | null>(null);
  const kpiIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchKpi = useCallback(async (termId: string) => {
    setKpiLoading(true);
    try {
      const token = localStorage.getItem('schoolbridge_access_token');
      const schoolId = localStorage.getItem('schoolbridge_active_school_id');
      const ts = Date.now();
      let url = `/api/v1/reports/kpi/?_ts=${ts}`;
      if (termId && termId !== 'current') url += `&term_id=${encodeURIComponent(termId)}`;
      const res = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(schoolId ? { 'X-School-ID': schoolId } : {}),
        },
      });
      if (!res.ok) throw new Error(`KPI fetch failed: HTTP ${res.status}`);
      const data: KpiData = await res.json();
      setKpi(data);
      setKpiLastUpdated(new Date());
    } catch (err) {
      console.error('[ReportsPage] KPI fetch error:', err);
    } finally {
      setKpiLoading(false);
    }
  }, []);

  // Fetch on mount and whenever selectedTermId changes
  useEffect(() => {
    fetchKpi(selectedTermId);
    // clear old interval and start a new one
    if (kpiIntervalRef.current) clearInterval(kpiIntervalRef.current);
    kpiIntervalRef.current = setInterval(() => fetchKpi(selectedTermId), 60_000);
    return () => { if (kpiIntervalRef.current) clearInterval(kpiIntervalRef.current); };
  }, [fetchKpi, selectedTermId]);

  // Re-fetch on window focus
  useEffect(() => {
    const onFocus = () => fetchKpi(selectedTermId);
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [fetchKpi, selectedTermId]);

  const refetchKpi = () => fetchKpi(selectedTermId);

  const terms: TermOption[] = kpi?.all_terms ?? [];
  const classes: ClassOption[] = kpi?.all_classes ?? [];

  // ── Generate report (JSON for on-screen view) ────────
  const handleGenerate = useCallback(async (overrideType?: ReportType | unknown) => {
    const targetType = (typeof overrideType === 'string' && overrideType) ? (overrideType as ReportType) : reportType;
    setGenerating(true);
    setReportResult(null);
    setReportError(null);
    try {
      const payload: Record<string, string> = { report_type: targetType, format: 'json' };
      if (selectedTermId) payload.term_id = selectedTermId;
      if (targetType === 'attendance_summary') {
        if (selectedClassId) payload.class_id = selectedClassId;
        payload.days = selectedDays;
      }
      const res = await apiClient.post('/reports/generate/', payload);
      setReportResult(res.data);
    } catch (e: unknown) {
      const respData = (e as any)?.response?.data;
      const msg = respData?.error
        || respData?.detail
        || (typeof respData === 'string' ? respData : null)
        || (e as Error)?.message
        || 'Failed to generate report. Check your selections and try again.';
      setReportError(msg);
    } finally {
      setGenerating(false);
    }
  }, [reportType, selectedTermId, selectedClassId, selectedDays]);

  const selectAndGenerateReport = useCallback((type: ReportType) => {
    setReportType(type);
    handleGenerate(type);
    const studio = document.getElementById('report-generator-studio');
    if (studio) {
      studio.scrollIntoView({ behavior: 'smooth' });
    }
  }, [handleGenerate]);

  // Auto-generate on initial page mount for immediate viewing (Test 11.1)
  useEffect(() => {
    handleGenerate();
  }, []);

  // ── Export generated report as file ─────────────────
  const handleExportReport = useCallback(async (exportFmt: string) => {
    setExportingFmt(exportFmt);
    try {
      const payload: Record<string, string> = { report_type: reportType, format: exportFmt };
      if (selectedTermId) payload.term_id = selectedTermId;
      if (reportType === 'attendance_summary') {
        if (selectedClassId) payload.class_id = selectedClassId;
        payload.days = selectedDays;
      }
      const res = await apiClient.post('/reports/generate/', payload, { responseType: 'blob' });
      const mimeType = exportFmt === 'pdf' ? 'application/pdf' : exportFmt === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      const blob = new Blob([res.data], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ext = exportFmt === 'pdf' ? 'pdf' : exportFmt === 'csv' ? 'csv' : 'xlsx';
      a.download = `${reportType}_${new Date().toISOString().split('T')[0]}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      let msg = 'Export failed. Please try again.';
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          msg = parsed.error || msg;
        } catch {
          // ignore
        }
      }
      alert(msg);
    } finally {
      setExportingFmt(null);
    }
  }, [reportType, selectedTermId, selectedClassId, selectedDays]);

  // ── Quick-export tile download ───────────────────────
  const handleQuickExport = useCallback(async (templateId: string, exportFmt: string) => {
    const key = `${templateId}-${exportFmt}`;
    setQuickExportingId(key);
    try {
      const res = await apiClient.post(
        '/reports/generate/',
        { report_type: templateId, format: exportFmt, term_id: selectedTermId || 'current' },
        { responseType: 'blob' }
      );
      const mimeType = exportFmt === 'pdf' ? 'application/pdf' : exportFmt === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      const blob = new Blob([res.data], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ext = exportFmt === 'csv' ? 'csv' : exportFmt === 'pdf' ? 'pdf' : 'xlsx';
      a.download = `${templateId}_${new Date().toISOString().split('T')[0]}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      let msg = `Download failed for ${templateId}. Please try again.`;
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          msg = parsed.error || msg;
        } catch {
          // ignore
        }
      }
      alert(msg);
    } finally {
      setQuickExportingId(null);
    }
  }, [selectedTermId]);

  const filteredTemplates = categoryFilter
    ? REPORT_TEMPLATES.filter((t) => t.category === categoryFilter)
    : REPORT_TEMPLATES;

  // ─────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* ── Page Header ───────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Reports &amp; UNEB Export</h1>
          <p className="text-xs text-slate-400 mt-1">
            Generate PDF, CSV, and XLSX reports — including live Fee Collection, Attendance, and UNEB UCE exports
            {kpiLastUpdated && (
              <span className="ml-2 px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono">
                Live · {kpiLastUpdated.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => refetchKpi()}
          disabled={kpiLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-slate-400 hover:text-slate-200 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${kpiLoading ? 'animate-spin text-emerald-400' : ''}`} /> Refresh Stats
        </button>
      </div>

      {/* ── Live KPI Cards ────────────────────────────── */}
      <StatGroup>
        <KpiCard
          title="Students Registered"
          value={kpiLoading ? '…' : (kpi?.students_registered?.toLocaleString() ?? '—')}
          change={kpiLoading ? 'Loading…' : (kpi?.current_term?.name ?? 'All Terms')}
          changeType="positive"
          subtitle="Click to view enrolment report"
          icon={<Users className="w-5 h-5 text-teal-400" />}
          isActive={reportType === 'enrolment'}
          onClick={() => selectAndGenerateReport('enrolment')}
          clickableHint="Generate report"
        />
        <KpiCard
          title="UNEB Candidates"
          value={kpiLoading ? '…' : (kpi?.uneb_candidates?.toLocaleString() ?? '—')}
          change="S.4 + P.7"
          changeType="positive"
          subtitle="Click to view candidate roster"
          icon={<GraduationCap className="w-5 h-5 text-emerald-400" />}
          isActive={reportType === 'uneb_registration'}
          onClick={() => selectAndGenerateReport('uneb_registration')}
          clickableHint="Generate export"
        />
        <KpiCard
          title="Fees Collected"
          value={kpiLoading ? '…' : (kpi ? `UGX ${fmt(kpi.total_collected_fees)}` : '—')}
          change={kpiLoading ? 'Loading…' : (kpi ? `${pct(kpi.collection_rate)} collection rate` : '—')}
          changeType={kpi && kpi.collection_rate >= 70 ? 'positive' : 'negative'}
          subtitle="Click to view fee breakdown"
          icon={<Banknote className="w-5 h-5 text-amber-400" />}
          isActive={reportType === 'fee_collection'}
          onClick={() => selectAndGenerateReport('fee_collection')}
          clickableHint="Generate report"
        />
        <KpiCard
          title="Outstanding Fees"
          value={kpiLoading ? '…' : (kpi ? `UGX ${fmt(kpi.outstanding_fees)}` : '—')}
          change={kpiLoading ? 'Loading…' : (kpi?.current_term?.name ?? 'All Terms')}
          changeType="negative"
          subtitle="Click to view fee defaulters"
          icon={<BarChart3 className="w-5 h-5 text-rose-400" />}
          isActive={reportType === 'defaulter_list'}
          onClick={() => selectAndGenerateReport('defaulter_list')}
          clickableHint="Generate report"
        />
      </StatGroup>

      {/* ── Report Generator Studio ───────────────────── */}
      <div id="report-generator-studio" className="bg-slate-800/80 border border-slate-700/60 rounded-2xl overflow-hidden scroll-mt-6">
        {/* Studio Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-700/60 bg-slate-900/50">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
            <BarChart3 className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">Report Generator Studio</h2>
            <p className="text-[11px] text-slate-400">Configure parameters then Generate — view on-screen or export to PDF/Excel</p>
          </div>
        </div>

        <div className="p-6 space-y-5">
          {/* Row 1: Report type + term */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Report Type */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Report Type</label>
              <div className="relative">
                <select
                  id="report-type-select"
                  value={reportType}
                  onChange={(e) => {
                    setReportType(e.target.value as ReportType);
                    setReportResult(null);
                    setReportError(null);
                  }}
                  className="w-full appearance-none bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 pr-10"
                >
                  <option value="fee_collection">Fee Collection &amp; Outstanding Balances</option>
                  <option value="attendance_summary">Attendance Summary</option>
                  <option value="student_roster">Student Roster</option>
                  <option value="defaulter_list">Fee Defaulters</option>
                  <option value="enrolment">Enrolment Report</option>
                  <option value="uneb_registration">UNEB UCE Registration</option>
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Term Selector */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Academic Term</label>
              <div className="relative">
                <select
                  id="term-select"
                  value={selectedTermId}
                  onChange={(e) => setSelectedTermId(e.target.value)}
                  className="w-full appearance-none bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 pr-10"
                >
                  <option value="current">Current Term (Auto)</option>
                  {terms.map((t) => (
                    <option key={t.id} value={String(t.id)}>
                      {t.name}{t.is_current ? ' ✓' : ''}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Conditional: Class (attendance) or spacer */}
            {reportType === 'attendance_summary' ? (
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Class</label>
                <div className="relative">
                  <select
                    id="class-select"
                    value={selectedClassId}
                    onChange={(e) => setSelectedClassId(e.target.value)}
                    className="w-full appearance-none bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 pr-10"
                  >
                    <option value="">All Classes</option>
                    {classes.map((c) => (
                      <option key={c.id} value={String(c.id)}>{c.name}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                </div>
              </div>
            ) : (
              <div className="hidden md:block" />
            )}
          </div>

          {/* Row 2: Date range (attendance only) */}
          {reportType === 'attendance_summary' && (
            <div className="flex flex-wrap gap-3">
              <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider self-center">Date Range:</label>
              {[
                { label: 'Full Term', value: '' },
                { label: 'Last 30 Days', value: '30' },
                { label: 'Last 14 Days', value: '14' },
                { label: 'Last 7 Days', value: '7' },
              ].map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => setSelectedDays(opt.value)}
                  className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all ${
                    selectedDays === opt.value
                      ? 'bg-emerald-500/10 border-emerald-500 text-emerald-400'
                      : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}

          {/* Generate Button */}
          <div className="flex items-center gap-3 pt-1">
            <Button
              id="btn-generate-report"
              variant="primary"
              size="md"
              leftIcon={generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              onClick={() => handleGenerate()}
              isLoading={generating}
              disabled={generating}
            >
              {generating ? 'Generating…' : 'Generate Report'}
            </Button>
            {reportResult && (
              <span className="text-xs text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Report ready
              </span>
            )}
          </div>

          {/* Error */}
          {reportError && (
            <div className="flex items-start gap-2 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-sm text-rose-400">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              {reportError}
            </div>
          )}
        </div>

        {/* ── Report Results Panel ─────────────────────── */}
        {reportResult && (
          <div className="border-t border-slate-700/60 bg-slate-900/30 p-6 space-y-5">
            {/* Export buttons */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h3 className="text-sm font-bold text-white">
                {isFeeReport(reportResult)
                  ? `Fee Collection — ${reportResult.term}`
                  : isAttReport(reportResult)
                    ? `Attendance — ${reportResult.class_name}`
                    : reportType === 'enrolment'
                      ? `Enrolment Report (${reportResult.total_active_students ?? 0} Active Students)`
                      : reportType === 'student_roster'
                        ? `Student Directory Roster (${reportResult.count ?? 0} Students)`
                        : reportType === 'defaulter_list'
                          ? `Fee Defaulters (${reportResult.count ?? 0} Flagged)`
                          : reportType === 'uneb_registration'
                            ? `UNEB UCE Candidates (${reportResult.count ?? 0} Candidates)`
                            : reportType === 'term_results'
                              ? `Term Results & Distribution (${reportResult.count ?? 0} Assessments)`
                              : reportType === 'result_slips'
                                ? `Student Result Slips (${reportResult.count ?? 0} Slips)`
                                : 'Report Results'}
              </h3>
              <div className="flex gap-2">
                {['uneb_registration', 'student_roster', 'defaulter_list', 'enrolment'].includes(reportType) && (
                  <button
                    id="btn-export-csv"
                    onClick={() => handleExportReport('csv')}
                    disabled={exportingFmt !== null}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-emerald-500/40 text-emerald-400 rounded-xl text-xs font-semibold uppercase tracking-wider hover:bg-emerald-500/10 transition-all disabled:opacity-40"
                  >
                    {exportingFmt === 'csv' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                    Export CSV
                  </button>
                )}
                <button
                  id="btn-export-pdf"
                  onClick={() => handleExportReport('pdf')}
                  disabled={exportingFmt !== null}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-rose-500/40 text-rose-400 rounded-xl text-xs font-semibold uppercase tracking-wider hover:bg-rose-500/10 transition-all disabled:opacity-40"
                >
                  {exportingFmt === 'pdf' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                  Export PDF
                </button>
                <button
                  id="btn-export-excel"
                  onClick={() => handleExportReport('excel')}
                  disabled={exportingFmt !== null}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-indigo-500/40 text-indigo-400 rounded-xl text-xs font-semibold uppercase tracking-wider hover:bg-indigo-500/10 transition-all disabled:opacity-40"
                >
                  {exportingFmt === 'excel' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                  Export Excel
                </button>
              </div>
            </div>

            {/* ── Fee Collection Results ─────────────── */}
            {isFeeReport(reportResult) && (
              <div className="space-y-4">
                {/* Summary KPI cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    {
                      label: 'Total Expected',
                      value: `UGX ${fmt(reportResult.total_expected)}`,
                      icon: <Banknote className="w-4 h-4 text-slate-400" />,
                      color: 'border-slate-700',
                    },
                    {
                      label: 'Collected',
                      value: `UGX ${fmt(reportResult.total_collected)}`,
                      icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
                      color: 'border-emerald-500/40',
                    },
                    {
                      label: 'Outstanding',
                      value: `UGX ${fmt(reportResult.outstanding)}`,
                      icon: <TrendingDown className="w-4 h-4 text-rose-400" />,
                      color: 'border-rose-500/40',
                    },
                    {
                      label: 'Collection Rate',
                      value: pct(reportResult.collection_rate),
                      icon: <BarChart3 className="w-4 h-4 text-amber-400" />,
                      color: 'border-amber-500/40',
                    },
                  ].map((card) => (
                    <div key={card.label} className={`bg-slate-800 border ${card.color} rounded-xl p-3`}>
                      <div className="flex items-center gap-2 mb-1">{card.icon}
                        <span className="text-[10px] text-slate-400 uppercase tracking-wider">{card.label}</span>
                      </div>
                      <div className="text-sm font-bold text-white">{card.value}</div>
                    </div>
                  ))}
                </div>

                {/* Per-class table */}
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Class</th>
                        <th className="px-4 py-3 text-right font-semibold">Students</th>
                        <th className="px-4 py-3 text-right font-semibold">Expected (UGX)</th>
                        <th className="px-4 py-3 text-right font-semibold">Collected (UGX)</th>
                        <th className="px-4 py-3 text-right font-semibold">Outstanding (UGX)</th>
                        <th className="px-4 py-3 text-right font-semibold">Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.by_class.map((row, i) => (
                        <tr
                          key={row.class}
                          className={`border-t border-slate-700/50 ${i % 2 === 0 ? '' : 'bg-slate-800/30'} hover:bg-slate-700/30 transition-colors`}
                        >
                          <td className="px-4 py-2.5 text-white font-medium">{row.class}</td>
                          <td className="px-4 py-2.5 text-slate-300 text-right">{row.students}</td>
                          <td className="px-4 py-2.5 text-slate-300 text-right">{fmt(row.expected)}</td>
                          <td className="px-4 py-2.5 text-emerald-400 text-right font-semibold">{fmt(row.collected)}</td>
                          <td className="px-4 py-2.5 text-rose-400 text-right font-semibold">{fmt(row.outstanding)}</td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={`font-bold ${row.collection_rate >= 70 ? 'text-emerald-400' : row.collection_rate >= 40 ? 'text-amber-400' : 'text-rose-400'}`}>
                              {pct(row.collection_rate)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.by_class.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No fee records found for this term.</div>
                  )}
                </div>
              </div>
            )}

            {/* ── Attendance Results ─────────────────── */}
            {isAttReport(reportResult) && (
              <div className="space-y-4">
                {/* Summary cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    {
                      label: 'Class',
                      value: reportResult.class_name,
                      icon: <Users className="w-4 h-4 text-slate-400" />,
                      color: 'border-slate-700',
                    },
                    {
                      label: 'Overall Rate',
                      value: pct(reportResult.overall_rate),
                      icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
                      color: 'border-emerald-500/40',
                    },
                    {
                      label: 'Total Present',
                      value: reportResult.total_present.toLocaleString(),
                      icon: <CheckCircle2 className="w-4 h-4 text-sky-400" />,
                      color: 'border-sky-500/40',
                    },
                    {
                      label: 'Total Absent',
                      value: reportResult.total_absent.toLocaleString(),
                      icon: <TrendingDown className="w-4 h-4 text-rose-400" />,
                      color: 'border-rose-500/40',
                    },
                  ].map((card) => (
                    <div key={card.label} className={`bg-slate-800 border ${card.color} rounded-xl p-3`}>
                      <div className="flex items-center gap-2 mb-1">{card.icon}
                        <span className="text-[10px] text-slate-400 uppercase tracking-wider">{card.label}</span>
                      </div>
                      <div className="text-sm font-bold text-white truncate">{card.value}</div>
                    </div>
                  ))}
                </div>

                {/* Daily breakdown table */}
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Date</th>
                        <th className="px-4 py-3 text-left font-semibold">Day</th>
                        <th className="px-4 py-3 text-right font-semibold">Present</th>
                        <th className="px-4 py-3 text-right font-semibold">Absent</th>
                        <th className="px-4 py-3 text-right font-semibold">Excused</th>
                        <th className="px-4 py-3 text-right font-semibold">Total</th>
                        <th className="px-4 py-3 text-right font-semibold">Rate %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.daily_breakdown.map((row, i) => (
                        <tr
                          key={row.date}
                          className={`border-t border-slate-700/50 ${i % 2 === 0 ? '' : 'bg-slate-800/30'} hover:bg-slate-700/30 transition-colors`}
                        >
                          <td className="px-4 py-2.5 text-white font-medium">{row.date}</td>
                          <td className="px-4 py-2.5 text-slate-400">{row.day_name}</td>
                          <td className="px-4 py-2.5 text-emerald-400 text-right font-semibold">{row.present_count}</td>
                          <td className="px-4 py-2.5 text-rose-400 text-right font-semibold">{row.absent_count}</td>
                          <td className="px-4 py-2.5 text-amber-400 text-right">{row.excused_count}</td>
                          <td className="px-4 py-2.5 text-slate-300 text-right">{row.total_students}</td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={`font-bold ${row.attendance_rate >= 80 ? 'text-emerald-400' : row.attendance_rate >= 60 ? 'text-amber-400' : 'text-rose-400'}`}>
                              {pct(row.attendance_rate)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.daily_breakdown.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">
                      No attendance records found for this date range.
                      <p className="text-xs mt-2 text-slate-600">
                        Try switching to <strong className="text-slate-400">Full Term</strong> to see all available attendance data.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Enrolment Results ───────────────────── */}
            {reportType === 'enrolment' && reportResult.classes && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <div className="bg-slate-800 border border-slate-700 rounded-xl p-3">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider">Total Active Students</span>
                    <div className="text-sm font-bold text-white mt-1">{reportResult.total_active_students?.toLocaleString() ?? 0}</div>
                  </div>
                  <div className="bg-slate-800 border border-slate-700 rounded-xl p-3">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider">Total Classes</span>
                    <div className="text-sm font-bold text-white mt-1">{reportResult.classes?.length ?? 0}</div>
                  </div>
                  <div className="bg-slate-800 border border-slate-700 rounded-xl p-3">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider">School</span>
                    <div className="text-sm font-bold text-white mt-1 truncate">{reportResult.school}</div>
                  </div>
                </div>
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Class</th>
                        <th className="px-4 py-3 text-left font-semibold">Level</th>
                        <th className="px-4 py-3 text-left font-semibold">Stream</th>
                        <th className="px-4 py-3 text-left font-semibold">Form Teacher</th>
                        <th className="px-4 py-3 text-right font-semibold">Male</th>
                        <th className="px-4 py-3 text-right font-semibold">Female</th>
                        <th className="px-4 py-3 text-right font-semibold">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.classes.map((c: any) => (
                        <tr key={c.class} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-2.5 text-white font-medium">{c.class}</td>
                          <td className="px-4 py-2.5 text-slate-300">{c.level}</td>
                          <td className="px-4 py-2.5 text-slate-300">{c.stream || '—'}</td>
                          <td className="px-4 py-2.5 text-slate-300">{c.form_teacher || '—'}</td>
                          <td className="px-4 py-2.5 text-slate-300 text-right">{c.male}</td>
                          <td className="px-4 py-2.5 text-slate-300 text-right">{c.female}</td>
                          <td className="px-4 py-2.5 text-emerald-400 text-right font-bold">{c.total}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.classes.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No classes found.</div>
                  )}
                </div>
              </div>
            )}

            {/* ── Student Roster Results ──────────────── */}
            {reportType === 'student_roster' && reportResult.students && (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Student ID</th>
                        <th className="px-4 py-3 text-left font-semibold">Full Name</th>
                        <th className="px-4 py-3 text-left font-semibold">Class</th>
                        <th className="px-4 py-3 text-left font-semibold">Gender</th>
                        <th className="px-4 py-3 text-left font-semibold">Primary Guardian</th>
                        <th className="px-4 py-3 text-left font-semibold">Guardian Phone</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.students.map((s: any) => (
                        <tr key={s.student_id} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-2.5 font-mono text-emerald-400 font-semibold">{s.student_id}</td>
                          <td className="px-4 py-2.5 text-white font-medium">{s.first_name} {s.last_name}</td>
                          <td className="px-4 py-2.5 text-slate-300">{s.class || '—'}</td>
                          <td className="px-4 py-2.5 text-slate-300">{s.gender}</td>
                          <td className="px-4 py-2.5 text-slate-300">{s.guardian || '—'}</td>
                          <td className="px-4 py-2.5 text-slate-300 font-mono">{s.guardian_phone || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.students.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No students found.</div>
                  )}
                </div>
              </div>
            )}

            {/* ── Fee Defaulters Results ──────────────── */}
            {reportType === 'defaulter_list' && reportResult.students && (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Student</th>
                        <th className="px-4 py-3 text-left font-semibold">ID</th>
                        <th className="px-4 py-3 text-left font-semibold">Class</th>
                        <th className="px-4 py-3 text-right font-semibold">Attendance Rate</th>
                        <th className="px-4 py-3 text-right font-semibold">Fee Paid %</th>
                        <th className="px-4 py-3 text-right font-semibold">Outstanding (UGX)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.students.map((d: any) => (
                        <tr key={d.student_id} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-2.5 text-white font-medium">{d.student}</td>
                          <td className="px-4 py-2.5 font-mono text-slate-300">{d.student_id}</td>
                          <td className="px-4 py-2.5 text-slate-300">{d.class || '—'}</td>
                          <td className="px-4 py-2.5 text-right font-semibold text-amber-400">{d.attendance_rate}%</td>
                          <td className="px-4 py-2.5 text-right font-semibold text-rose-400">{d.fee_payment_rate}%</td>
                          <td className="px-4 py-2.5 text-right font-bold text-rose-400">{fmt(d.outstanding_balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.students.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No defaulters flagged for this term (all accounts compliant).</div>
                  )}
                </div>
              </div>
            )}

            {/* ── UNEB Registration Results ───────────── */}
            {reportType === 'uneb_registration' && reportResult.candidates && (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Candidate ID</th>
                        <th className="px-4 py-3 text-left font-semibold">Candidate Full Name</th>
                        <th className="px-4 py-3 text-left font-semibold">Candidate Class</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.candidates.map((c: any) => (
                        <tr key={c.student_id} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-2.5 font-mono text-emerald-400 font-semibold">{c.student_id}</td>
                          <td className="px-4 py-2.5 text-white font-medium">{c.name}</td>
                          <td className="px-4 py-2.5 text-slate-300">{c.class || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.candidates.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No UNEB candidates (S.4 / P.7) registered yet.</div>
                  )}
                </div>
              </div>
            )}

            {/* ── Term Results ────────────────────────── */}
            {reportType === 'term_results' && reportResult.results && (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Class</th>
                        <th className="px-4 py-3 text-left font-semibold">Subject</th>
                        <th className="px-4 py-3 text-left font-semibold">Assessment</th>
                        <th className="px-4 py-3 text-left font-semibold">Type</th>
                        <th className="px-4 py-3 text-right font-semibold">Max Marks</th>
                        <th className="px-4 py-3 text-left font-semibold">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.results.map((r: any, i: number) => (
                        <tr key={i} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-2.5 text-white font-medium">{r.class}</td>
                          <td className="px-4 py-2.5 text-slate-300">{r.subject}</td>
                          <td className="px-4 py-2.5 text-slate-300">{r.assessment}</td>
                          <td className="px-4 py-2.5 text-slate-300">{r.type}</td>
                          <td className="px-4 py-2.5 text-slate-300 text-right font-semibold">{r.max_marks}</td>
                          <td className="px-4 py-2.5">
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                              {r.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.results.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No assessments recorded for this term.</div>
                  )}
                </div>
              </div>
            )}

            {/* ── Result Slips ────────────────────────── */}
            {reportType === 'result_slips' && reportResult.slips && (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-xl border border-slate-700">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400 uppercase tracking-wider">
                        <th className="px-4 py-3 text-left font-semibold">Student ID</th>
                        <th className="px-4 py-3 text-left font-semibold">Full Name</th>
                        <th className="px-4 py-3 text-left font-semibold">Class</th>
                        <th className="px-4 py-3 text-left font-semibold">Batch Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportResult.slips.map((s: any) => (
                        <tr key={s.student_id} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-2.5 font-mono text-emerald-400 font-semibold">{s.student_id}</td>
                          <td className="px-4 py-2.5 text-white font-medium">{s.name}</td>
                          <td className="px-4 py-2.5 text-slate-300">{s.class || '—'}</td>
                          <td className="px-4 py-2.5 text-emerald-400 font-semibold">Ready to Print</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {reportResult.slips.length === 0 && (
                    <div className="py-10 text-center text-slate-500 text-sm">No students available for result slips.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Quick Export Tile Grid ────────────────────── */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-bold text-white">Quick Export</h2>
          <div className="flex flex-wrap gap-2">
            {[
              { value: '', label: 'All Reports' },
              { value: 'academic', label: 'Academic' },
              { value: 'financial', label: 'Financial' },
              { value: 'attendance', label: 'Attendance' },
              { value: 'uneb', label: 'UNEB' },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setCategoryFilter(opt.value)}
                className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all ${
                  categoryFilter === opt.value
                    ? 'bg-emerald-500/10 border-emerald-500 text-emerald-400'
                    : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredTemplates.map((template) => (
            <div
              key={template.id}
              className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 flex flex-col gap-4 hover:border-slate-600 transition-all"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center ${categoryColor[template.category]}`}>
                    {template.category === 'academic' && <GraduationCap className="w-4 h-4" />}
                    {template.category === 'financial' && <Banknote className="w-4 h-4" />}
                    {template.category === 'attendance' && <CalendarCheck className="w-4 h-4" />}
                    {template.category === 'uneb' && <FileText className="w-4 h-4" />}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">{template.name}</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">{template.description}</p>
                  </div>
                </div>
                <Badge variant={categoryBadge[template.category]} size="sm">
                  {template.category.toUpperCase()}
                </Badge>
              </div>

              <div className="flex flex-wrap gap-2 pt-1 border-t border-slate-700/60">
                {template.formats.map((fmtKey) => {
                  const isLoading = quickExportingId === `${template.id}-${fmtKey}`;
                  const fmtColors: Record<string, string> = {
                    pdf: 'text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/40',
                    csv: 'text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/40',
                    excel: 'text-indigo-400 hover:bg-indigo-500/10 hover:border-indigo-500/40',
                  };
                  return (
                    <button
                      key={fmtKey}
                      id={`quick-export-${template.id}-${fmtKey}`}
                      onClick={() => handleQuickExport(template.id, fmtKey)}
                      disabled={!!quickExportingId}
                      className={`flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all disabled:opacity-40 ${fmtColors[fmtKey] ?? ''}`}
                    >
                      {isLoading ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Download className="w-3 h-3" />
                      )}
                      {fmtKey}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── UNEB Bulk Export Callout ──────────────────── */}
      <div className="p-5 bg-gradient-to-r from-indigo-900/40 to-purple-900/30 border border-indigo-500/30 rounded-2xl flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <FileDown className="w-6 h-6 text-indigo-400" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white">UNEB UCE Registration Bulk Export</h4>
            <p className="text-xs text-slate-400 mt-0.5">
              Export all S4 candidates in the UNEB-required CSV format for direct upload to the UNEB Online Registration Portal.
            </p>
          </div>
        </div>
        <div className="flex-shrink-0">
          <Button
            id="btn-export-uneb-csv"
            variant="primary"
            size="sm"
            leftIcon={quickExportingId === 'uneb_registration-csv' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
            onClick={() => handleQuickExport('uneb_registration', 'csv')}
            isLoading={quickExportingId === 'uneb_registration-csv'}
          >
            Export UNEB CSV
          </Button>
        </div>
      </div>
    </div>
  );
};
