import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SearchableSelect, type SelectOption } from '../../components/attendance/SearchableSelect';
import { apiClient } from '../../api/client';
import {
  CheckCircle2,
  Clock,
  Check,
  X,
  Loader2,
  Calendar,
  Save,
  CheckCheck,
  Users,
  AlertCircle,
  AlertTriangle,
  Info,
  Sparkles,
  Lock,
} from 'lucide-react';
import { AutoSuggestInput } from '../../components/ui/AutoSuggestInput';

export type AttendanceStatus = 'present' | 'late' | 'absent' | 'excused' | 'not_marked';

export interface RosterStudent {
  id: string; // student UUID
  regNo: string;
  name: string;
  status: AttendanceStatus;
  notes: string;
}

// ── Compatibility exports for ViewClassAttendancesPage ─────────────────────────
export const FULL_CLASS_OPTIONS: SelectOption[] = [
  { value: 'p1', label: 'Primary 1 (P.1)' },
  { value: 'p2', label: 'Primary 2 (P.2)' },
  { value: 'p3', label: 'Primary 3 (P.3)' },
  { value: 'p4', label: 'Primary 4 (P.4)' },
  { value: 'p5', label: 'Primary 5 (P.5)' },
  { value: 'p6', label: 'Primary 6 (P.6)' },
  { value: 'p7', label: 'Primary 7 (P.7)' },
  { value: 's1', label: 'Senior 1 (S.1)' },
  { value: 's2', label: 'Senior 2 (S.2)' },
  { value: 's3', label: 'Senior 3 (S.3)' },
  { value: 's4', label: 'Senior 4 (S.4)' },
  { value: 's5', label: 'Senior 5 (S.5)' },
  { value: 's6', label: 'Senior 6 (S.6)' },
];

export function getStreamsForClass(_classIdOrName?: string): SelectOption[] {
  return [
    { value: 'East', label: 'East Stream' },
    { value: 'West', label: 'West Stream' },
    { value: 'Stream A', label: 'Stream A' },
    { value: 'Stream B', label: 'Stream B' },
  ];
}

export function getSubjectsForClass(_classIdOrName?: string): SelectOption[] {
  return [
    { value: 'Mathematics', label: 'Mathematics' },
    { value: 'English Language', label: 'English Language' },
    { value: 'Science', label: 'Science' },
    { value: 'Social Studies (SST)', label: 'Social Studies (SST)' },
  ];
}

export const AttendanceRegisterPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const storedClassId = sessionStorage.getItem('attendance_class_id') || '';
  const storedDate = sessionStorage.getItem('attendance_date') || '';

  const urlClassId = searchParams.get('class_id') || storedClassId;
  const urlDate = searchParams.get('date') || storedDate;

  // Today's ISO date string (YYYY-MM-DD)
  const getTodayIso = () => {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const todayIso = getTodayIso();

  // Filter Selection State
  const [classOptions, setClassOptions] = useState<SelectOption[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string>(urlClassId || '');
  const [selectedClassName, setSelectedClassName] = useState<string>('');
  const [sessionDate, setSessionDate] = useState<string>(urlDate || todayIso);

  // Loading & Roster State
  const [isInitializing, setIsInitializing] = useState<boolean>(true);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [isRosterLoaded, setIsRosterLoaded] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isLockedForToday, setIsLockedForToday] = useState<boolean>(false);

  // Student Roster
  const [roster, setRoster] = useState<RosterStudent[]>([]);

  // Confirmation / Error Banner
  const [banner, setBanner] = useState<{
    type: 'success' | 'error' | 'warning';
    title: string;
    message: string;
  } | null>(null);

  // Sync state to URL search parameters & sessionStorage so refreshing retains class and date
  useEffect(() => {
    if (selectedClassId && sessionDate) {
      setSearchParams({ class_id: selectedClassId, date: sessionDate }, { replace: true });
      sessionStorage.setItem('attendance_class_id', selectedClassId);
      sessionStorage.setItem('attendance_date', sessionDate);
    }
  }, [selectedClassId, sessionDate, setSearchParams]);

  // Formatted date string for Ugandan display (e.g. Friday, 04 September 2026)
  const formattedSessionDate = React.useMemo(() => {
    if (!sessionDate) return '';
    try {
      const [year, month, day] = sessionDate.split('-').map(Number);
      const d = new Date(year, month - 1, day);
      return d.toLocaleDateString('en-GB', {
        weekday: 'long',
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return sessionDate;
    }
  }, [sessionDate]);

  const isToday = sessionDate === todayIso;

  // ── 1. Fetch Classes dynamically from Backend (once on mount) ────────────
  useEffect(() => {
    setIsInitializing(true);
    const initialClassId = searchParams.get('class_id') || sessionStorage.getItem('attendance_class_id') || '';
    apiClient
      .get('/students/classes/')
      .then((res) => {
        const classes = res.data?.results || res.data || [];
        if (Array.isArray(classes) && classes.length > 0) {
          const opts: SelectOption[] = classes.map((c: any) => ({
            value: String(c.id),
            label: c.name || `Class ${c.level} ${c.stream || ''}`.trim(),
          }));

          setClassOptions(opts);

          // Priority: 1. URL/session param, 2. Form class assigned to this teacher (e.g. P.5 East), 3. First class
          let defaultClass = opts[0];
          if (initialClassId) {
            const match = opts.find((o) => o.value === initialClassId);
            if (match) defaultClass = match;
          } else {
            // Find P.5 East if available or teacher's assigned class
            const p5East = opts.find((o) => o.label.toLowerCase().includes('p.5 east'));
            if (p5East) defaultClass = p5East;
          }

          setSelectedClassId(defaultClass.value);
          setSelectedClassName(defaultClass.label);
        }
      })
      .catch((err) => {
        console.error('Failed to load class list', err);
      })
      .finally(() => {
        setIsInitializing(false);
      });
  }, []); // Run once only on mount

  // ── 2. Fetch Class Attendance Register from Backend API ───────────────────
  const fetchRegisterForClassAndDate = useCallback((classId: string, date: string, preserveBanner: boolean = false) => {
    if (!classId) return;

    setIsFetching(true);
    if (!preserveBanner) {
      setBanner(null);
    }

    // Fetch from official attendance register endpoint
    apiClient
      .get('/attendance/register/', {
        params: {
          class_id: classId,
          date: date,
        },
      })
      .then((res) => {
        const data = res.data;
        const records = data?.records || [];
        const isLocked = Boolean(data?.is_locked);
        setIsLockedForToday(isLocked);

        if (Array.isArray(records) && records.length > 0) {
          const mapped: RosterStudent[] = records.map((rec: any, idx: number) => {
            const rawStatus = (rec.status || 'not_marked').toLowerCase();
            const validStatus: AttendanceStatus =
              rawStatus === 'present' || rawStatus === 'late' || rawStatus === 'absent' || rawStatus === 'excused'
                ? rawStatus
                : 'not_marked';

            return {
              id: String(rec.student_id || rec.student || rec.id),
              regNo: rec.student_reg_no || rec.reg_number || `STD-${String(idx + 1).padStart(3, '0')}`,
              name: rec.student_name || `Student ${idx + 1}`,
              status: validStatus,
              notes: rec.notes || rec.pre_excused_reason || '',
            };
          });

          setRoster(mapped);
        } else {
          // Fallback to student directory roster if no attendance records yet
          setIsLockedForToday(false);
          return apiClient.get('/students/', { params: { current_class: classId, page_size: 200, is_active: 'true' } }).then((stuRes) => {
            const students = stuRes.data?.results || stuRes.data || [];
            if (Array.isArray(students)) {
              const mapped: RosterStudent[] = students.map((st: any, idx: number) => ({
                id: String(st.id),
                regNo: st.student_id || `STD-${String(idx + 1).padStart(3, '0')}`,
                name: `${st.first_name || ''} ${st.last_name || ''}`.trim() || `Student ${idx + 1}`,
                status: 'not_marked',
                notes: '',
              }));
              setRoster(mapped);
            } else {
              setRoster([]);
            }
          });
        }
      })
      .catch((err) => {
        console.error('Failed to load register', err);
        // If teacher permission error
        if (err.response?.status === 403) {
          const detail = err.response?.data?.detail;
          const error = err.response?.data?.error;
          const msg =
            typeof detail === 'string'
              ? detail
              : typeof detail === 'object' && detail?.detail
              ? String(detail.detail)
              : typeof error === 'string'
              ? error
              : 'You are only permitted to view and submit attendance for your assigned class.';
          setBanner({
            type: 'warning',
            title: 'Permission Restricted',
            message: msg,
          });
        }
        setRoster([]);
      })
      .finally(() => {
        setIsFetching(false);
        setIsRosterLoaded(true);
      });
  }, []);

  // Auto-fetch when selectedClassId or sessionDate changes
  useEffect(() => {
    if (selectedClassId && sessionDate) {
      fetchRegisterForClassAndDate(selectedClassId, sessionDate);
    }
  }, [selectedClassId, sessionDate, fetchRegisterForClassAndDate]);

  // Handle Class Change
  const handleClassChange = (newClassId: string) => {
    setSelectedClassId(newClassId);
    const found = classOptions.find((c) => c.value === newClassId);
    if (found) {
      setSelectedClassName(found.label);
    }
  };

  // Update Individual Student Status
  const updateStudentStatus = (studentId: string, status: AttendanceStatus) => {
    setRoster((prev) =>
      prev.map((student) => (student.id === studentId ? { ...student, status } : student))
    );
  };

  // Update Individual Student Note (e.g. Late or Absent Reason)
  const updateStudentNote = (studentId: string, notes: string) => {
    setRoster((prev) =>
      prev.map((student) => (student.id === studentId ? { ...student, notes } : student))
    );
  };

  // Bulk Apply Reason to all students with a specific status (e.g. all Excused or all Late)
  const [bulkExcusedReason, setBulkExcusedReason] = useState('');
  const [bulkLateReason, setBulkLateReason] = useState('');

  const applyBulkReasonToStatus = (targetStatus: AttendanceStatus, bulkReason: string) => {
    if (!bulkReason.trim()) return;
    setRoster((prev) =>
      prev.map((s) => (s.status === targetStatus ? { ...s, notes: bulkReason.trim() } : s))
    );
  };

  // Mark All Present Shortcut
  const handleMarkAllPresent = () => {
    setRoster((prev) => prev.map((s) => ({ ...s, status: 'present' })));
  };

  // ── 3. Submit Register ───────────────────────────────────────────────────
  const handleSubmitRegister = () => {
    if (roster.length === 0 || !selectedClassId) return;

    setIsSaving(true);

    const payload = {
      class_id: selectedClassId,
      date: sessionDate,
      attendance: roster.map((r) => ({
        student_id: r.id,
        status: r.status === 'not_marked' ? 'absent' : r.status,
        notes: r.notes.trim(),
      })),
    };

    apiClient
      .post('/attendance/register/', payload)
      .then((res) => {
        // Mark register as locked immediately — no re-fetch needed
        setIsLockedForToday(true);

        const msg =
          res.data?.message ||
          `Attendance locked for today. Daily register for ${selectedClassName} on ${formattedSessionDate} has been successfully recorded.`;

        setBanner({
          type: 'success',
          title: '✅ Success — Attendance locked for today',
          message: msg.includes('locked') ? msg : `Attendance locked for today. ${msg}`,
        });

        // Smooth scroll to top so confirmation banner is visible immediately
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .catch((err) => {
        console.error('Failed to submit attendance', err);
        const rawDetail = err.response?.data?.detail;
        const errMsg =
          typeof err.response?.data?.message === 'string'
            ? err.response?.data?.message
            : typeof err.response?.data?.error === 'string'
            ? err.response?.data?.error
            : typeof rawDetail === 'string'
            ? rawDetail
            : typeof rawDetail === 'object' && rawDetail?.detail
            ? String(rawDetail.detail)
            : 'Failed to submit attendance register. Please try again.';
        setBanner({
          type: 'error',
          title: 'Submission Failed',
          message: errMsg,
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .finally(() => {
        setIsSaving(false);
      });
  };

  // Compute status counts
  const stats = React.useMemo(() => {
    let present = 0;
    let late = 0;
    let absent = 0;
    let excused = 0;
    let notMarked = 0;

    roster.forEach((s) => {
      if (s.status === 'present') present++;
      else if (s.status === 'late') late++;
      else if (s.status === 'absent') absent++;
      else if (s.status === 'excused') excused++;
      else notMarked++;
    });

    return { present, late, absent, excused, notMarked, total: roster.length };
  }, [roster]);

  return (
    <div className="space-y-6">
      {/* ── Page Header ───────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Calendar className="w-6 h-6 text-emerald-400" />
            Daily Attendance Register
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Mark and submit class attendance registers with real-time backend persistence.
          </p>
        </div>

        {/* Today's Official School Date Chip & Locked Indicator */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          <div className="bg-slate-800/90 border border-slate-700/80 px-3 py-1.5 rounded-xl shadow-inner text-xs flex items-center gap-2">
            <Clock className="w-4 h-4 text-teal-400" />
            <span className="text-slate-400">School Date:</span>
            <span className="font-semibold text-white">{formattedSessionDate}</span>
            {isToday && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Today
              </span>
            )}
          </div>
          {isLockedForToday && (
            <span className="px-2.5 py-1.5 rounded-xl text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 shadow-sm animate-in fade-in">
              <Lock className="w-3.5 h-3.5 text-emerald-400" />
              Attendance locked for today
            </span>
          )}
        </div>
      </div>

      {/* ── Confirmation / Alert Banner ───────────────────────────────── */}
      {banner && (
        <div
          className={`p-4 rounded-xl border flex items-start gap-3 transition-all animate-in fade-in-50 ${
            banner.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : banner.type === 'error'
              ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
              : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
          }`}
        >
          {banner.type === 'success' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : banner.type === 'error' ? (
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          )}
          <div className="flex-1">
            <h3 className="text-sm font-bold">{banner.title}</h3>
            <p className="text-xs opacity-90 mt-0.5">{typeof banner.message === 'string' ? banner.message : String((banner.message as any)?.detail || banner.message)}</p>
          </div>
          <button
            onClick={() => setBanner(null)}
            className="text-xs opacity-70 hover:opacity-100 p-1"
            aria-label="Dismiss banner"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ── Top Filter Bar Card ───────────────────────────────────────── */}
      <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 items-end">
          
          {/* Class Selector */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Select Class Stream
            </label>
            {isInitializing ? (
              <div className="h-11 bg-slate-700/40 rounded-xl animate-pulse flex items-center px-4 text-xs text-slate-400">
                Loading classes...
              </div>
            ) : (
              <SearchableSelect
                label=""
                options={classOptions}
                value={selectedClassId}
                onChange={handleClassChange}
                placeholder="Select class stream..."
              />
            )}
          </div>

          {/* Date Picker with "Today" Shortcut */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                Attendance Date
              </label>
              {!isToday && (
                <button
                  type="button"
                  onClick={() => setSessionDate(todayIso)}
                  className="text-[11px] font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
                >
                  Set to Today
                </button>
              )}
            </div>

            <div className="relative">
              <input
                type="date"
                value={sessionDate}
                onChange={(e) => setSessionDate(e.target.value)}
                className="w-full h-11 px-4 bg-slate-900/90 border border-slate-700 rounded-xl text-sm font-semibold text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all cursor-pointer"
              />
            </div>
          </div>

          {/* Action: Reload / Refresh Register */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => fetchRegisterForClassAndDate(selectedClassId, sessionDate)}
              disabled={isFetching || !selectedClassId}
              className="h-11 px-5 w-full bg-slate-700/60 hover:bg-slate-700 text-white text-xs font-semibold rounded-xl flex items-center justify-center gap-2 border border-slate-600 transition-all disabled:opacity-50"
            >
              {isFetching ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Loading Register...</span>
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 text-emerald-400" />
                  <span>Fetch Register</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* ── Attendance Register Table Section ──────────────────────────── */}
      {isRosterLoaded && (
        <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl space-y-5 animate-in fade-in-50 duration-300">
          
          {/* Header Bar: Class Context & Summary Badges */}
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-700/60">
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                <span>{selectedClassName || 'Selected Class'}</span>
                <span className="text-slate-500">•</span>
                <span className="text-sm font-normal text-slate-300">{formattedSessionDate}</span>
              </h2>

              {/* Status Counters */}
              <div className="flex items-center gap-2.5 mt-2 flex-wrap text-xs">
                <span className="px-2.5 py-1 rounded-lg bg-slate-900 text-slate-300 border border-slate-700 font-medium">
                  Total: <strong className="text-white">{stats.total}</strong>
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                  Present: <strong>{stats.present}</strong>
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/20 font-medium">
                  Late: <strong>{stats.late}</strong>
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 font-medium">
                  Absent: <strong>{stats.absent}</strong>
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-sky-500/10 text-sky-300 border border-sky-500/20 font-medium">
                  Excused: <strong>{stats.excused}</strong>
                </span>
                {stats.notMarked > 0 && (
                  <span className="px-2.5 py-1 rounded-lg bg-slate-700/50 text-slate-400 border border-slate-600 font-medium">
                    Unmarked: <strong>{stats.notMarked}</strong>
                  </span>
                )}
              </div>
            </div>

            {/* Quick Actions: Mark All & Submit Register */}
            <div className="flex items-center gap-3 self-end lg:self-center">
              <button
                type="button"
                onClick={handleMarkAllPresent}
                disabled={roster.length === 0}
                className="h-10 px-4 rounded-xl bg-slate-700/80 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-600 flex items-center gap-1.5 transition-all disabled:opacity-50"
              >
                <CheckCheck className="w-4 h-4 text-emerald-400" />
                <span>Mark All Present</span>
              </button>

              {banner?.type === 'success' && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-in fade-in">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Attendance submitted successfully
                </span>
              )}

              <button
                type="button"
                id="top-submit-register-btn"
                onClick={handleSubmitRegister}
                disabled={isSaving || isLockedForToday || roster.length === 0}
                className={`h-10 px-6 rounded-xl text-white text-xs font-bold shadow-lg flex items-center gap-2 transition-all active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed ${
                  isLockedForToday
                    ? 'bg-slate-600 shadow-slate-900/30'
                    : 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/30'
                }`}
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Submitting...</span>
                  </>
                ) : isLockedForToday ? (
                  <>
                    <Lock className="w-4 h-4" />
                    <span>Register Submitted</span>
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    <span>Submit Register</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* ── Bulk Reason Quick-Apply Toolbars (When Multiple Excused/Late Students) ── */}
          {stats.excused > 1 && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-sky-500/10 border border-sky-500/25 rounded-xl p-3 text-xs text-sky-300">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-sky-400 shrink-0" />
                <span className="font-semibold text-white">
                  Common Reason for {stats.excused} Excused Students:
                </span>
              </div>
              <div className="flex items-center gap-2 flex-1 max-w-lg">
                <AutoSuggestInput
                  category="excused_reasons"
                  value={bulkExcusedReason}
                  onChange={setBulkExcusedReason}
                  placeholder="Auto-suggest common reason (e.g. Clinic visit, Parent called)..."
                  inputClassName="h-8 text-xs bg-slate-900/90 border-sky-500/40 focus:ring-sky-400"
                  showChips={false}
                />
                <button
                  type="button"
                  onClick={() => applyBulkReasonToStatus('excused', bulkExcusedReason)}
                  disabled={!bulkExcusedReason.trim()}
                  className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all shrink-0"
                >
                  Apply to All ({stats.excused})
                </button>
              </div>
            </div>
          )}

          {stats.late > 1 && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-amber-500/10 border border-amber-500/25 rounded-xl p-3 text-xs text-amber-300">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
                <span className="font-semibold text-white">
                  Common Reason for {stats.late} Late Students:
                </span>
              </div>
              <div className="flex items-center gap-2 flex-1 max-w-lg">
                <AutoSuggestInput
                  category="late_reasons"
                  value={bulkLateReason}
                  onChange={setBulkLateReason}
                  placeholder="Auto-suggest common late reason (e.g. Heavy rain, Traffic)..."
                  inputClassName="h-8 text-xs bg-slate-900/90 border-amber-500/40 focus:ring-amber-400"
                  showChips={false}
                />
                <button
                  type="button"
                  onClick={() => applyBulkReasonToStatus('late', bulkLateReason)}
                  disabled={!bulkLateReason.trim()}
                  className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all shrink-0"
                >
                  Apply to All ({stats.late})
                </button>
              </div>
            </div>
          )}

          {/* Roster Table */}
          {roster.length === 0 ? (
            <div className="p-10 text-center bg-slate-900/40 rounded-xl border border-slate-700/60 space-y-3">
              <Users className="w-10 h-10 mx-auto text-slate-500" />
              <h3 className="text-sm font-bold text-white">No Enrolled Students Found</h3>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                No active students are currently assigned to <strong className="text-slate-200">{selectedClassName}</strong>.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-700/60 shadow-md">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-900/80 border-b border-slate-700 text-slate-400 uppercase tracking-wider">
                    <th className="py-3.5 px-4 font-bold w-12 text-center">#</th>
                    <th className="py-3.5 px-4 font-bold">Student</th>
                    <th className="py-3.5 px-4 font-bold text-center">Current Status</th>
                    <th className="py-3.5 px-4 font-bold text-center">Attendance Action</th>
                    <th className="py-3.5 px-4 font-bold">Reason / Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50 bg-slate-800/40">
                  {roster.map((student, idx) => (
                    <tr key={student.id} className="hover:bg-slate-700/20 transition-colors">
                      {/* Index */}
                      <td className="py-3 px-4 text-center font-mono text-slate-400">
                        {idx + 1}
                      </td>

                      {/* Student Info */}
                      <td className="py-3 px-4">
                        <p className="text-sm font-bold text-white tracking-tight">{student.name}</p>
                        <p className="text-[11px] text-slate-400 font-mono mt-0.5">{student.regNo}</p>
                      </td>

                      {/* Status Badge */}
                      <td className="py-3 px-4 text-center">
                        {student.status === 'present' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            Present
                          </span>
                        )}
                        {student.status === 'late' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/10 text-amber-300 border border-amber-500/20">
                            Late
                          </span>
                        )}
                        {student.status === 'absent' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                            Absent
                          </span>
                        )}
                        {student.status === 'excused' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-sky-500/10 text-sky-300 border border-sky-500/20">
                            Excused
                          </span>
                        )}
                        {student.status === 'not_marked' && (
                          <span className="text-slate-500 italic text-xs">
                            Not Marked
                          </span>
                        )}
                      </td>

                      {/* 4 Action Buttons: Present, Late, Absent, Excused */}
                      <td className="py-3 px-4">
                        <div className="flex items-center justify-center gap-1.5 flex-wrap">
                          <button
                            type="button"
                            onClick={() => updateStudentStatus(student.id, 'present')}
                            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                              student.status === 'present'
                                ? 'bg-emerald-600 text-white shadow-md shadow-emerald-900/30 ring-1 ring-emerald-400'
                                : 'bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white'
                            }`}
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>Present</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => updateStudentStatus(student.id, 'late')}
                            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                              student.status === 'late'
                                ? 'bg-amber-600 text-white shadow-md shadow-amber-900/30 ring-1 ring-amber-400'
                                : 'bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white'
                            }`}
                          >
                            <Clock className="w-3.5 h-3.5" />
                            <span>Late</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => updateStudentStatus(student.id, 'absent')}
                            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                              student.status === 'absent'
                                ? 'bg-rose-600 text-white shadow-md shadow-rose-900/30 ring-1 ring-rose-400'
                                : 'bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white'
                            }`}
                          >
                            <X className="w-3.5 h-3.5" />
                            <span>Absent</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => updateStudentStatus(student.id, 'excused')}
                            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                              student.status === 'excused'
                                ? 'bg-sky-600 text-white shadow-md shadow-sky-900/30 ring-1 ring-sky-400'
                                : 'bg-slate-900 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white'
                            }`}
                          >
                            <Info className="w-3.5 h-3.5" />
                            <span>Excused</span>
                          </button>
                        </div>
                      </td>

                      {/* Reason / Notes AutoSuggest Input */}
                      <td className="py-3 px-4 min-w-[260px]">
                        <AutoSuggestInput
                          value={student.notes}
                          onChange={(val) => updateStudentNote(student.id, val)}
                          category={
                            student.status === 'excused'
                              ? 'excused_reasons'
                              : student.status === 'late'
                              ? 'late_reasons'
                              : student.status === 'absent'
                              ? 'absence_reasons'
                              : 'attendance_notes'
                          }
                          placeholder={
                            student.status === 'excused'
                              ? 'Type or select excused reason (e.g. Clinic visit)...'
                              : student.status === 'late'
                              ? 'Type or select late reason (e.g. Rain, Traffic)...'
                              : student.status === 'absent'
                              ? 'Type or select absence note...'
                              : 'Optional notes / remarks...'
                          }
                          inputClassName={
                            student.status === 'excused'
                              ? 'border-sky-500/50 focus:ring-sky-400'
                              : student.status === 'late'
                              ? 'border-amber-500/50 focus:ring-amber-400'
                              : student.status === 'absent'
                              ? 'border-rose-500/50 focus:ring-rose-400'
                              : 'border-slate-700 focus:ring-emerald-400'
                          }
                          showChips={false}
                          enableHistory={true}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Bottom Submit Bar */}
          {roster.length > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-700/60">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xs text-slate-400">
                  Register for <strong>{selectedClassName}</strong> on {formattedSessionDate}
                </span>
                {banner?.type === 'success' && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-in fade-in">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Attendance submitted successfully
                  </span>
                )}
              </div>

              <button
                type="button"
                id="submit-register-btn"
                onClick={handleSubmitRegister}
                disabled={isSaving || isLockedForToday || roster.length === 0}
                className={`h-10 px-8 rounded-xl text-white text-xs font-bold shadow-lg flex items-center gap-2 transition-all active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed ${
                  isLockedForToday
                    ? 'bg-slate-600 shadow-slate-900/30'
                    : 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/30'
                }`}
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Submitting Register...</span>
                  </>
                ) : isLockedForToday ? (
                  <>
                    <Lock className="w-4 h-4" />
                    <span>Register Submitted</span>
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    <span>Submit Register</span>
                  </>
                )}
              </button>
            </div>
          )}

        </div>
      )}
    </div>
  );
};

export default AttendanceRegisterPage;
