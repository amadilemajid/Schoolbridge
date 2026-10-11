import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import {
  Loader2, Users, AlertTriangle, Calendar, ChevronDown,
  CalendarRange, RefreshCw
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────
interface SelectOption {
  value: string;
  label: string;
}

interface DayRecord {
  date: string;
  label: string;
  status: 'present' | 'late' | 'absent' | 'excused' | 'not_marked';
  notes?: string;
}

interface StudentRow {
  studentId: string;
  name: string;
  regNo: string;
  days: DayRecord[];
  presentCount: number;
  lateCount: number;
  absentCount: number;
  excusedCount: number;
  rate: number;
}

// ── Pure helpers ─────────────────────────────────────────────────────────────
function getTodayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function offsetIsoBy(baseIso: string, days: number): string {
  if (!baseIso) return baseIso;
  const parts = baseIso.split('-').map(Number);
  if (parts.length !== 3 || parts.some(isNaN)) return baseIso;
  const [y, m, d] = parts;
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + days);
  const ny = dt.getFullYear();
  const nm = String(dt.getMonth() + 1).padStart(2, '0');
  const nd = String(dt.getDate()).padStart(2, '0');
  return `${ny}-${nm}-${nd}`;
}

function isoToShortLabel(iso: string): string {
  if (!iso) return '';
  const parts = iso.split('-').map(Number);
  if (parts.length !== 3 || parts.some(isNaN)) return iso;
  const [y, m, d] = parts;
  const dt = new Date(y, m - 1, d);
  const dayName = dt.toLocaleDateString('en-GB', { weekday: 'short' });
  return `${dayName} ${d}`;
}

function buildDateRange(from: string, to: string): string[] {
  if (!from || !to || from > to) return [];
  const result: string[] = [];
  let cur = from;
  // Cap at 35 days to prevent browser performance bottlenecks
  while (cur <= to && result.length < 35) {
    result.push(cur);
    const next = offsetIsoBy(cur, 1);
    if (!next || next <= cur) break;
    cur = next;
  }
  return result;
}

const today = getTodayIso();

const QUICK_RANGES = [
  { label: 'Today',        from: () => today,                  to: () => today },
  { label: 'Last 7 Days',  from: () => offsetIsoBy(today, -6), to: () => today },
  { label: 'Last 14 Days', from: () => offsetIsoBy(today, -13),to: () => today },
  { label: 'Last 30 Days', from: () => offsetIsoBy(today, -29),to: () => today },
];

const STATUS_STYLE: Record<string, { label: string; className: string }> = {
  present:    { label: 'P', className: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' },
  late:       { label: 'L', className: 'bg-amber-500/20 text-amber-300 border border-amber-500/30' },
  absent:     { label: 'A', className: 'bg-rose-500/20 text-rose-400 border border-rose-500/30' },
  excused:    { label: 'E', className: 'bg-sky-500/20 text-sky-300 border border-sky-500/30' },
  not_marked: { label: '—', className: 'text-slate-600' },
};

// ── Component ─────────────────────────────────────────────────────────────────
export const ViewClassAttendancesPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const urlClassId  = searchParams.get('class_id') || sessionStorage.getItem('attendance_class_id') || '';
  const urlDateFrom = searchParams.get('date_from') || '';
  const urlDateTo   = searchParams.get('date_to') || '';

  // ── Filter state ──────────────────────────────────────────────────────────
  const [classOptions, setClassOptions]       = useState<SelectOption[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string>(urlClassId);
  const [selectedClassName, setSelectedClassName] = useState<string>('');
  const [dateFrom, setDateFrom]               = useState<string>(urlDateFrom || offsetIsoBy(today, -6));
  const [dateTo, setDateTo]                   = useState<string>(urlDateTo || today);
  const [activeQuick, setActiveQuick]         = useState<string>(
    urlDateFrom || urlDateTo ? '' : 'Last 7 Days'
  );

  // ── Load / data state ─────────────────────────────────────────────────────
  const [isInitializing, setIsInitializing] = useState<boolean>(true);
  const [isFetching, setIsFetching]         = useState<boolean>(false);
  const [fetchError, setFetchError]         = useState<string | null>(null);
  const [rows, setRows]                     = useState<StudentRow[]>([]);
  const [dates, setDates]                   = useState<string[]>([]);
  const [hasLoaded, setHasLoaded]           = useState<boolean>(false);
  const [fetchTrigger, setFetchTrigger]     = useState<number>(0);

  // Active fetch tracking ref to eliminate race conditions and avoid stuck loading states
  const activeFetchIdRef = useRef<number>(0);

  // Sync filters to URL query params
  useEffect(() => {
    if (selectedClassId && dateFrom && dateTo) {
      setSearchParams(
        { class_id: selectedClassId, date_from: dateFrom, date_to: dateTo },
        { replace: true }
      );
      sessionStorage.setItem('attendance_class_id', selectedClassId);
    }
  }, [selectedClassId, dateFrom, dateTo, setSearchParams]);

  // ── 1. Load classes once on mount ─────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setIsInitializing(true);

    apiClient.get('/students/classes/')
      .then(res => {
        if (cancelled) return;
        const raw: any[] = res.data?.results || res.data || [];
        const opts: SelectOption[] = Array.isArray(raw)
          ? raw.map((c: any) => ({
              value: String(c.id),
              label: c.name || `Class ${c.level || ''} ${c.stream || ''}`.trim(),
            }))
          : [];

        setClassOptions(opts);

        if (opts.length > 0) {
          // Priority: 1. URL param, 2. P.5 East (teacher assigned class), 3. First class
          let target = opts[0];
          if (urlClassId) {
            const match = opts.find(o => o.value === urlClassId);
            if (match) target = match;
          } else {
            const p5 = opts.find(o => o.label.toLowerCase().includes('p.5 east') || o.label.toLowerCase().includes('p.5'));
            if (p5) target = p5;
          }
          setSelectedClassId(target.value);
          setSelectedClassName(target.label);
        }
      })
      .catch(err => {
        if (!cancelled) {
          console.error('Failed to load class list', err);
          setClassOptions([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsInitializing(false);
        }
      });

    return () => { cancelled = true; };
  }, []); // Run once only on mount

  // ── 2. Fetch attendance whenever class, date range, or fetchTrigger changes ──
  useEffect(() => {
    if (isInitializing || !selectedClassId || !dateFrom || !dateTo) {
      return;
    }

    if (dateFrom > dateTo) {
      setFetchError("'From' date cannot be after 'To' date.");
      return;
    }

    const dateList = buildDateRange(dateFrom, dateTo);
    if (dateList.length === 0) {
      setFetchError("Please select a valid date range.");
      return;
    }

    const currentFetchId = ++activeFetchIdRef.current;
    setIsFetching(true);
    setFetchError(null);
    setDates(dateList);

    Promise.all([
      apiClient.get('/students/', {
        params: { current_class: selectedClassId, is_active: 'true', page_size: 200 },
      }),
      apiClient.get('/attendance/records/', {
        params: { class_id: selectedClassId, date_from: dateFrom, date_to: dateTo, page_size: 500 },
      }),
    ])
      .then(([studRes, recRes]) => {
        if (currentFetchId !== activeFetchIdRef.current) return;

        const students: any[] = studRes.data?.results || studRes.data || [];
        const records: any[]  = recRes.data?.results  || recRes.data  || [];

        // Build lookup: studentId → date → {status, notes}
        const lookup: Record<string, Record<string, { status: string; notes: string }>> = {};
        records.forEach((r: any) => {
          const sid = String(r.student_id || r.student || '');
          const dt  = String(r.date || '');
          if (sid && dt) {
            if (!lookup[sid]) lookup[sid] = {};
            lookup[sid][dt] = { status: r.status || 'not_marked', notes: r.notes || '' };
          }
        });

        const built: StudentRow[] = students.map((st: any) => {
          const sid   = String(st.id);
          const name  = `${st.first_name || ''} ${st.last_name || ''}`.trim() || 'Student';
          const regNo = st.student_id || st.admission_number || '—';

          let present = 0, late = 0, absent = 0, excused = 0;
          const dayRecords: DayRecord[] = dateList.map(iso => {
            const rec    = lookup[sid]?.[iso];
            const status = (rec?.status || 'not_marked') as DayRecord['status'];
            if (status === 'present')    present++;
            else if (status === 'late')  late++;
            else if (status === 'absent') absent++;
            else if (status === 'excused') excused++;
            return { date: iso, label: isoToShortLabel(iso), status, notes: rec?.notes };
          });

          const marked = present + late + absent + excused;
          const rate   = marked > 0 ? Math.round(((present + late) / marked) * 100) : 0;
          return {
            studentId: sid,
            name,
            regNo,
            days: dayRecords,
            presentCount: present,
            lateCount: late,
            absentCount: absent,
            excusedCount: excused,
            rate,
          };
        });

        setRows(built);
        setHasLoaded(true);
        setIsFetching(false);
      })
      .catch(err => {
        if (currentFetchId !== activeFetchIdRef.current) return;

        const msg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to load attendance records.';
        setFetchError(typeof msg === 'string' ? msg : 'Failed to load attendance records.');
        setRows([]);
        setHasLoaded(true);
        setIsFetching(false);
      });

  }, [isInitializing, selectedClassId, dateFrom, dateTo, fetchTrigger]);

  // ── Summary stats ─────────────────────────────────────────────────────────
  const summary = useMemo(() => {
    let present = 0, late = 0, absent = 0, excused = 0;
    rows.forEach(r => {
      present += r.presentCount;
      late    += r.lateCount;
      absent  += r.absentCount;
      excused += r.excusedCount;
    });
    const total = present + late + absent + excused;
    return {
      present,
      late,
      absent,
      excused,
      total,
      rate: total > 0 ? Math.round(((present + late) / total) * 100) : 0,
    };
  }, [rows]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleClassChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    setSelectedClassId(v);
    setSelectedClassName(classOptions.find(o => o.value === v)?.label || '');
  };

  const applyQuickRange = (preset: typeof QUICK_RANGES[0]) => {
    setDateFrom(preset.from());
    setDateTo(preset.to());
    setActiveQuick(preset.label);
  };

  const handleRefresh = () => {
    setFetchTrigger(prev => prev + 1);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <CalendarRange className="w-6 h-6 text-blue-400" />
            Class Attendance History
            {isFetching && hasLoaded && (
              <Loader2 className="w-4 h-4 animate-spin text-blue-400 ml-1" />
            )}
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            View daily attendance records across a date range for any class.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isFetching || isInitializing}
          className="self-start sm:self-auto h-9 px-4 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-semibold border border-slate-600 flex items-center gap-2 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* ── Filter Panel ── */}
      <div className="bg-slate-800/90 border border-slate-700/60 rounded-xl p-5 space-y-4 shadow-lg">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          
          {/* Class selector */}
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">Class</label>
            {isInitializing ? (
              <div className="h-10 rounded-xl bg-slate-700/50 animate-pulse flex items-center px-3 text-xs text-slate-400">
                Loading classes...
              </div>
            ) : (
              <div className="relative">
                <select
                  value={selectedClassId}
                  onChange={handleClassChange}
                  className="w-full h-10 pl-3 pr-8 rounded-xl bg-slate-900/80 border border-slate-700 text-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                >
                  {classOptions.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              </div>
            )}
          </div>

          {/* From date */}
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">From</label>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              <input
                type="date"
                value={dateFrom}
                max={dateTo}
                onChange={e => {
                  setDateFrom(e.target.value);
                  setActiveQuick('');
                }}
                className="w-full h-10 pl-9 pr-3 rounded-xl bg-slate-900/80 border border-slate-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 [color-scheme:dark]"
              />
            </div>
          </div>

          {/* To date */}
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">To</label>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              <input
                type="date"
                value={dateTo}
                min={dateFrom}
                max={today}
                onChange={e => {
                  setDateTo(e.target.value);
                  setActiveQuick('');
                }}
                className="w-full h-10 pl-9 pr-3 rounded-xl bg-slate-900/80 border border-slate-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 [color-scheme:dark]"
              />
            </div>
          </div>
        </div>

        {/* Quick presets */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500 font-semibold uppercase tracking-wider mr-1">Quick:</span>
          {QUICK_RANGES.map(preset => (
            <button
              key={preset.label}
              type="button"
              onClick={() => applyQuickRange(preset)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                activeQuick === preset.label
                  ? 'bg-blue-600 border-blue-500 text-white shadow-md shadow-blue-900/30 font-bold'
                  : 'bg-slate-900/60 border-slate-700 text-slate-300 hover:border-blue-500/50 hover:text-white'
              }`}
            >
              {preset.label}
            </button>
          ))}
          {dates.length > 0 && (
            <span className="ml-auto text-[11px] text-slate-500">
              Showing {dates.length} day{dates.length !== 1 ? 's' : ''} · Max 35
            </span>
          )}
        </div>
      </div>

      {/* ── Summary stats (shown once loaded) ── */}
      {hasLoaded && rows.length > 0 && (
        <div className={`grid grid-cols-2 sm:grid-cols-5 gap-3 transition-opacity duration-200 ${isFetching ? 'opacity-60' : 'opacity-100'}`}>
          {[
            { label: 'Students', value: rows.length,        cls: 'text-white' },
            { label: 'Present',  value: summary.present,    cls: 'text-emerald-400' },
            { label: 'Late',     value: summary.late,       cls: 'text-amber-300' },
            { label: 'Absent',   value: summary.absent,     cls: 'text-rose-400' },
            { label: 'Avg Rate', value: `${summary.rate}%`, cls: summary.rate >= 75 ? 'text-emerald-400' : 'text-rose-400' },
          ].map(stat => (
            <div key={stat.label} className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3.5 text-center">
              <p className={`text-2xl font-extrabold ${stat.cls}`}>{stat.value}</p>
              <p className="text-[11px] text-slate-400 mt-0.5 font-medium">{stat.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Initial Load Spinner (only shown on true first load) ── */}
      {isFetching && !hasLoaded && (
        <div className="flex items-center justify-center py-20 gap-3 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
          <span className="text-sm">Loading attendance records…</span>
        </div>
      )}

      {/* ── Error Banner ── */}
      {fetchError && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{fetchError}</span>
        </div>
      )}

      {/* ── Empty state ── */}
      {!isFetching && hasLoaded && !fetchError && rows.length === 0 && (
        <div className="p-10 text-center bg-slate-900/40 rounded-xl border border-slate-700/60 space-y-3">
          <Users className="w-10 h-10 mx-auto text-slate-500" />
          <h3 className="text-sm font-bold text-white">No Students Found</h3>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            No active students are enrolled in <strong className="text-slate-200">{selectedClassName || 'this class'}</strong>.
          </p>
        </div>
      )}

      {/* ── Attendance Grid ── */}
      {hasLoaded && rows.length > 0 && (
        <div className={`bg-slate-800/90 border border-slate-700/60 rounded-xl shadow-xl overflow-hidden transition-opacity duration-200 ${isFetching ? 'opacity-60' : 'opacity-100'}`}>

          {/* Grid header */}
          <div className="px-5 py-3.5 border-b border-slate-700/60 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <span>{selectedClassName || 'Class Attendance'}</span>
              <span className="text-slate-500">•</span>
              <span className="text-xs font-normal text-slate-300">
                {dateFrom === dateTo ? isoToShortLabel(dateFrom) : `${dateFrom} to ${dateTo}`}
              </span>
            </h2>
            <div className="flex items-center gap-3 text-[11px] text-slate-400 flex-wrap">
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/30 border border-emerald-500/40 inline-block" /> Present (P)</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-500/30 border border-amber-500/40 inline-block" /> Late (L)</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-rose-500/30 border border-rose-500/40 inline-block" /> Absent (A)</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-sky-500/30 border border-sky-500/40 inline-block" /> Excused (E)</span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-slate-900/70 border-b border-slate-700/60 text-slate-400">
                  <th className="py-3 px-4 font-bold text-left sticky left-0 bg-slate-900/95 z-10 min-w-[170px] border-r border-slate-700/40">
                    Student
                  </th>
                  {dates.map(iso => (
                    <th
                      key={iso}
                      className={`py-3 px-2 font-bold text-center min-w-[50px] ${iso === today ? 'text-blue-400 bg-blue-500/5' : ''}`}
                    >
                      <div>{isoToShortLabel(iso)}</div>
                      {iso === today && <div className="text-[9px] font-normal text-blue-400/80 leading-none mt-0.5">Today</div>}
                    </th>
                  ))}
                  <th className="py-3 px-4 font-bold text-center min-w-[68px] text-slate-300 sticky right-0 bg-slate-900/95 border-l border-slate-700/40">
                    Rate
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/40">
                {rows.map(row => (
                  <tr key={row.studentId} className="hover:bg-slate-700/20 transition-colors">
                    {/* Sticky student name column */}
                    <td className="py-2.5 px-4 sticky left-0 bg-slate-800/95 z-10 border-r border-slate-700/40">
                      <p className="font-bold text-white truncate max-w-[155px]">{row.name}</p>
                      <p className="text-[10px] text-slate-400 font-mono">{row.regNo}</p>
                    </td>

                    {/* Per-day status cells */}
                    {row.days.map(day => {
                      const style = STATUS_STYLE[day.status] ?? STATUS_STYLE['not_marked'];
                      return (
                        <td key={day.date} className="py-2.5 px-2 text-center" title={day.notes ? `${day.status} — ${day.notes}` : day.status}>
                          <span className={`inline-flex items-center justify-center w-8 h-7 rounded-lg font-bold text-[11px] ${style.className}`}>
                            {style.label}
                          </span>
                        </td>
                      );
                    })}

                    {/* Rate (sticky right) */}
                    <td className="py-2.5 px-4 text-center sticky right-0 bg-slate-800/95 border-l border-slate-700/40">
                      <span className={`font-bold text-sm ${row.rate >= 75 ? 'text-emerald-400' : row.rate >= 50 ? 'text-amber-400' : 'text-rose-400'}`}>
                        {row.rate}%
                      </span>
                      <div className="text-[10px] text-slate-500 leading-none mt-0.5">
                        {row.presentCount + row.lateCount}/{row.days.length}d
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Footer legend */}
          <div className="px-5 py-3 border-t border-slate-700/40 text-[11px] text-slate-500 flex flex-wrap gap-x-4 gap-y-1">
            <span>P = Present · L = Late · A = Absent · E = Excused · — = Not recorded</span>
            <span className="ml-auto">Rate = (Present + Late) ÷ Total recorded days</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default ViewClassAttendancesPage;
