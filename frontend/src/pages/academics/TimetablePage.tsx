/**
 * TimetablePage.tsx
 *
 * PRODUCTION-READY Class Timetable System.
 *
 * All data fetched dynamically from the backend — zero hardcoded values:
 *   • Class streams   → GET /students/classes/
 *   • Academic terms  → GET /schools/terms/
 *   • Timetable slots → GET /timetable/versions/?class_group=<id>&academic_term=<id>&is_active=true
 *   • Subjects        → GET /results/subjects/?class_group=<id>
 *   • Staff           → GET /metadata/lookups/staff/
 *   • Conflict check  → GET /timetable/versions/<id>/validate-conflicts/
 *   • Slot update     → PATCH /timetable/slots/<id>/
 *   • Slot create     → POST /timetable/slots/
 *   • Version create  → POST /timetable/versions/
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import {
  BookOpen, User, ArrowLeft, Calendar, AlertTriangle, Clock,
  ChevronDown, Printer, Edit3, X, Check,
  Sparkles, RefreshCw, AlertCircle, ShieldCheck,
  Send, MessageSquare
} from 'lucide-react';
import { Link } from 'react-router-dom';

// ── API Types ─────────────────────────────────────────────────────────────────

interface ClassGroup {
  id: string | number;
  name: string;
  level: string;
  stream?: string;
  is_active?: boolean;
}

interface AcademicTerm {
  id: string | number;
  name: string;
  is_current?: boolean;
  academic_year_year?: number;
  term_number?: number;
  start_date?: string;
  end_date?: string;
}

interface Subject {
  id: number | string;
  name: string;
  code: string;
  class_levels?: string;
  is_active?: boolean;
}

interface StaffMember {
  id: string;
  full_name: string;
  email: string;
  role: string;
}

interface TimetableSlot {
  id: string;
  day_of_week: number;
  day_name: string;
  period_number: number;
  start_time: string;
  end_time: string;
  subject?: number | string | null;
  subject_name?: string;
  subject_display: string;
  teacher?: string | null;
  teacher_name?: string | null;
  room?: string;
  slot_type: 'lesson' | 'break' | 'assembly' | 'lunch' | 'study' | string;
}

interface TimetableVersion {
  id: string;
  class_group: string | number;
  class_group_name: string;
  academic_term: string | number;
  term_name: string;
  version_number: number;
  is_active: boolean;
  effective_from: string;
  notes: string;
  slots: TimetableSlot[];
}

interface ConflictItem {
  teacher: string;
  day: string;
  time: string;
  class_1: string;
  class_2: string;
  subject_1: string;
  subject_2: string;
}

// ── Day column definitions ───────────────────────────────────────────────────
const DAY_MAP: { id: number; label: string }[] = [
  { id: 0, label: 'Monday' },
  { id: 1, label: 'Tuesday' },
  { id: 2, label: 'Wednesday' },
  { id: 3, label: 'Thursday' },
  { id: 4, label: 'Friday' },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(t: string): string {
  return t ? t.slice(0, 5) : '';
}

function isBreakRow(slot: TimetableSlot): boolean {
  return slot.slot_type === 'break' || slot.slot_type === 'assembly' || slot.slot_type === 'lunch';
}

function breakLabel(slot: TimetableSlot): string {
  if (slot.slot_type === 'lunch') return '🍲 Lunch Break & Rest';
  if (slot.slot_type === 'assembly') return '📢 Morning Assembly';
  return '☕ Tea Break';
}

/** Rich color palettes per curriculum category */
function getSubjectBadgeStyle(name: string): { bg: string; text: string; border: string; dot: string } {
  const n = (name || '').toLowerCase();
  if (n.includes('math') || n.includes('pmtc') || n.includes('smtc')) {
    return { bg: 'bg-blue-500/10 hover:bg-blue-500/15', text: 'text-blue-300', border: 'border-blue-500/30', dot: 'bg-blue-400' };
  }
  if (n.includes('phys') || n.includes('chem') || n.includes('bio') || n.includes('scie') || n.includes('agri')) {
    return { bg: 'bg-emerald-500/10 hover:bg-emerald-500/15', text: 'text-emerald-300', border: 'border-emerald-500/30', dot: 'bg-emerald-400' };
  }
  if (n.includes('hist') || n.includes('geog') || n.includes('soci') || n.includes('econ') || n.includes('div') || n.includes('cre') || n.includes('ire')) {
    return { bg: 'bg-amber-500/10 hover:bg-amber-500/15', text: 'text-amber-300', border: 'border-amber-500/30', dot: 'bg-amber-400' };
  }
  if (n.includes('engl') || n.includes('lit') || n.includes('kisw') || n.includes('luga') || n.includes('fren')) {
    return { bg: 'bg-purple-500/10 hover:bg-purple-500/15', text: 'text-purple-300', border: 'border-purple-500/30', dot: 'bg-purple-400' };
  }
  if (n.includes('ict') || n.includes('comp') || n.includes('sict')) {
    return { bg: 'bg-cyan-500/10 hover:bg-cyan-500/15', text: 'text-cyan-300', border: 'border-cyan-500/30', dot: 'bg-cyan-400' };
  }
  if (n.includes('art') || n.includes('ent') || n.includes('pe') || n.includes('general paper') || n.includes('gp')) {
    return { bg: 'bg-rose-500/10 hover:bg-rose-500/15', text: 'text-rose-300', border: 'border-rose-500/30', dot: 'bg-rose-400' };
  }
  return { bg: 'bg-slate-800/80 hover:bg-slate-800', text: 'text-slate-200', border: 'border-slate-700/60', dot: 'bg-slate-400' };
}
function normalizeTimeString(val: string): string {
  if (!val) return '';
  const trimmed = val.trim();
  const match12 = trimmed.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)$/i);
  if (match12) {
    let hours = parseInt(match12[1], 10);
    const minutes = match12[2];
    const seconds = match12[3] || '00';
    const ampm = match12[4].toUpperCase();
    if (ampm === 'PM' && hours < 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;
    return `${String(hours).padStart(2, '0')}:${minutes}:${seconds}`;
  }
  const match24 = trimmed.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (match24) {
    const hours = String(parseInt(match24[1], 10)).padStart(2, '0');
    const minutes = match24[2];
    const seconds = match24[3] || '00';
    return `${hours}:${minutes}:${seconds}`;
  }
  return trimmed;
}

function parseApiError(err: any): string {
  if (!err) return 'An unexpected error occurred.';
  if (typeof err === 'string') return err;
  const data = err.response?.data || err;
  if (typeof data === 'string') return data;
  
  const extractStrings = (obj: any): string[] => {
    if (!obj) return [];
    if (typeof obj === 'string') return [obj];
    if (Array.isArray(obj)) return obj.flatMap(extractStrings);
    if (typeof obj === 'object') {
      return Object.entries(obj).flatMap(([key, val]) => {
        if (key === 'status_code') return [];
        const msgs = extractStrings(val);
        if (key === 'non_field_errors' || key === 'detail' || key === 'error') {
          return msgs;
        }
        return msgs.map((m) => `${key}: ${m}`);
      });
    }
    return [String(obj)];
  };

  const msgs = extractStrings(data);
  return msgs.length > 0 ? msgs.join('. ') : 'Failed to save slot changes. Please check for scheduling conflicts.';
}

// ── Component ─────────────────────────────────────────────────────────────────

export const TimetablePage: React.FC = () => {
  const { tenant } = useAuth();
  const queryClient = useQueryClient();

  const [selectedClassId, setSelectedClassId] = useState<string>('');
  const [selectedTermId, setSelectedTermId] = useState<string>('');
  const [showConflictsModal, setShowConflictsModal] = useState<boolean>(false);
  const [isCreatingVersion, setIsCreatingVersion] = useState<boolean>(false);
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [publishSuccessMsg, setPublishSuccessMsg] = useState<string>('');
  const [showWhatsAppPreview, setShowWhatsAppPreview] = useState<boolean>(false);
  const [whatsAppPreviewText, setWhatsAppPreviewText] = useState<string>('');

  // Slot edit modal state
  const [editingSlot, setEditingSlot] = useState<TimetableSlot | null>(null);
  const [editSubjectId, setEditSubjectId] = useState<string>('');
  const [editTeacherId, setEditTeacherId] = useState<string>('');
  const [editRoom, setEditRoom] = useState<string>('');
  const [editSlotType, setEditSlotType] = useState<string>('lesson');
  const [editStartTime, setEditStartTime] = useState<string>('08:00');
  const [editEndTime, setEditEndTime] = useState<string>('09:00');
  const [isSavingSlot, setIsSavingSlot] = useState<boolean>(false);
  const [saveSlotError, setSaveSlotError] = useState<string>('');

  // ── 1. Fetch class groups (active only) ──────────────────────────────────
  const { data: classData, isLoading: classesLoading } = useQuery({
    queryKey: ['class-groups'],
    queryFn: async () => {
      const res = await apiClient.get('/students/classes/', {
        params: { is_active: 'true' },
      });
      return (res.data?.results || res.data || []) as ClassGroup[];
    },
  });
  const classes: ClassGroup[] = classData || [];

  // Group classes by level category for the dropdown
  const primaryClasses = classes.filter((c) => /^(Baby|Middle|Top|Nursery|P\d)/i.test(c.level || c.name));
  const oLevelClasses = classes.filter((c) => /^S[1-4]$/i.test(c.level || ''));
  const aLevelClasses = classes.filter((c) => /^S[5-6]$/i.test(c.level || ''));
  const otherClasses = classes.filter(
    (c) => !primaryClasses.includes(c) && !oLevelClasses.includes(c) && !aLevelClasses.includes(c)
  );

  // ── 2. Fetch terms ────────────────────────────────────────────────────────
  const { data: termData, isLoading: termsLoading } = useQuery({
    queryKey: ['academic-terms'],
    queryFn: async () => {
      const res = await apiClient.get('/schools/terms/');
      return (res.data?.results || res.data || []) as AcademicTerm[];
    },
  });
  const terms: AcademicTerm[] = termData || [];

  // Auto-select current term
  useEffect(() => {
    if (terms.length > 0 && !selectedTermId) {
      const current = terms.find((t) => t.is_current) || terms[0];
      setSelectedTermId(String(current.id));
    }
  }, [terms, selectedTermId]);

  // Auto-select first class
  useEffect(() => {
    if (classes.length > 0 && !selectedClassId) {
      setSelectedClassId(String(classes[0].id));
    }
  }, [classes, selectedClassId]);

  // ── 3. Fetch active timetable version for selected class + term ───────────
  const {
    data: versionData,
    isLoading: timetableLoading,
    error: timetableError,
    refetch: refetchTimetable,
  } = useQuery({
    queryKey: ['timetable-version', selectedClassId, selectedTermId],
    queryFn: async () => {
      const res = await apiClient.get('/timetable/versions/', {
        params: {
          class_group: selectedClassId,
          academic_term: selectedTermId,
          is_active: 'true',
        },
      });
      const list: TimetableVersion[] = res.data?.results || res.data || [];
      return list[0] || null;
    },
    enabled: !!selectedClassId && !!selectedTermId,
  });

  const activeVersion: TimetableVersion | null = versionData || null;
  const slots: TimetableSlot[] = activeVersion?.slots || [];

  // ── 4. Fetch subjects for selected class ──────────────────────────────────
  const { data: classSubjects = [] } = useQuery({
    queryKey: ['class-subjects', selectedClassId],
    queryFn: async () => {
      if (!selectedClassId) return [];
      const res = await apiClient.get('/results/subjects/', {
        params: { class_group: selectedClassId },
      });
      return (res.data?.results || res.data || []) as Subject[];
    },
    enabled: !!selectedClassId,
  });

  // ── 5. Fetch staff members for teacher assignment ─────────────────────────
  const { data: staffList = [] } = useQuery({
    queryKey: ['staff-lookup'],
    queryFn: async () => {
      const res = await apiClient.get('/metadata/lookups/staff/');
      return (res.data?.results || res.data || []) as StaffMember[];
    },
  });

  // ── 6. Check conflicts for active version ─────────────────────────────────
  const { data: conflictData } = useQuery({
    queryKey: ['timetable-conflicts', activeVersion?.id],
    queryFn: async () => {
      if (!activeVersion?.id) return { conflicts: [] };
      const res = await apiClient.get(`/timetable/versions/${activeVersion.id}/validate-conflicts/`);
      return res.data as { conflicts: ConflictItem[] };
    },
    enabled: !!activeVersion?.id,
  });

  const conflicts: ConflictItem[] = conflictData?.conflicts || [];

  // ── Derive unique time-slot rows from API slots ───────────────────────────
  const uniqueTimeRows: TimetableSlot[] = useMemo(() => {
    if (slots.length === 0) return [];
    const seen = new Set<string>();
    const rows: TimetableSlot[] = [];
    const sorted = [...slots].sort((a, b) => a.start_time.localeCompare(b.start_time));
    for (const s of sorted) {
      if (!seen.has(s.start_time)) {
        seen.add(s.start_time);
        rows.push(s);
      }
    }
    return rows;
  }, [slots]);

  const getSlot = (dayId: number, startTime: string): TimetableSlot | undefined => {
    return slots.find((s) => s.day_of_week === dayId && s.start_time === startTime);
  };

  // ── Modal Actions ─────────────────────────────────────────────────────────
  // ── Modal Actions ─────────────────────────────────────────────────────────
  const openEditModal = (slot: TimetableSlot) => {
    setEditingSlot(slot);
    setEditSubjectId(slot.subject ? String(slot.subject) : '');
    setEditTeacherId(slot.teacher ? String(slot.teacher) : '');
    setEditRoom(slot.room || '');
    setEditSlotType(slot.slot_type || 'lesson');
    setEditStartTime(fmtTime(slot.start_time) || '08:00');
    setEditEndTime(fmtTime(slot.end_time) || '09:00');
    setSaveSlotError('');
  };

  const openCreateModal = (dayId: number, dayLabel: string, periodNumber: number, startTime: string, endTime: string) => {
    setEditingSlot({
      id: '',
      day_of_week: dayId,
      day_name: dayLabel,
      period_number: periodNumber,
      start_time: startTime || '08:00',
      end_time: endTime || '09:00',
      subject: null,
      subject_display: '',
      teacher: null,
      room: '',
      slot_type: 'lesson',
    });
    setEditSubjectId('');
    setEditTeacherId('');
    setEditRoom('');
    setEditSlotType('lesson');
    setEditStartTime(fmtTime(startTime) || '08:00');
    setEditEndTime(fmtTime(endTime) || '09:00');
    setSaveSlotError('');
  };

  const closeEditModal = () => {
    setEditingSlot(null);
    setSaveSlotError('');
  };

  const handleSaveSlot = async () => {
    if (!editingSlot) return;
    const normStart = normalizeTimeString(editStartTime);
    const normEnd = normalizeTimeString(editEndTime);

    if (normStart && normEnd && normStart >= normEnd) {
      setSaveSlotError('End time must be after start time.');
      return;
    }
    setIsSavingSlot(true);
    setSaveSlotError('');

    try {
      const payload: Record<string, any> = {
        slot_type: editSlotType,
        subject: editSlotType === 'lesson' && editSubjectId ? editSubjectId : null,
        teacher: editSlotType !== 'break' && editSlotType !== 'lunch' && editTeacherId ? editTeacherId : null,
        room: editRoom.trim(),
        start_time: normStart,
        end_time: normEnd,
      };

      if (editingSlot.id) {
        await apiClient.patch(`/timetable/slots/${editingSlot.id}/`, payload);
      } else {
        await apiClient.post(`/timetable/slots/`, {
          ...payload,
          timetable_version: activeVersion?.id,
          day_of_week: editingSlot.day_of_week,
          period_number: editingSlot.period_number,
        });
      }

      await queryClient.invalidateQueries({ queryKey: ['timetable-version', selectedClassId, selectedTermId] });
      await queryClient.invalidateQueries({ queryKey: ['timetable-conflicts', activeVersion?.id] });
      closeEditModal();
    } catch (err: any) {
      setSaveSlotError(parseApiError(err));
    } finally {
      setIsSavingSlot(false);
    }
  };

  // ── Generate default timetable for class without one ──────────────────────
  const handleCreateStarterTimetable = async () => {
    if (!selectedClassId || !selectedTermId) return;
    setIsCreatingVersion(true);

    try {
      // 1. Create active TimetableVersion
      await apiClient.post('/timetable/versions/', {
        class_group: selectedClassId,
        academic_term: selectedTermId,
        version_number: 1,
        is_active: true,
        effective_from: new Date().toISOString().split('T')[0],
        notes: `Standard schedule generated for ${classLabel}`,
      });

      // 2. Refetch timetable to load slots
      await queryClient.invalidateQueries({ queryKey: ['timetable-version', selectedClassId, selectedTermId] });
      refetchTimetable();
    } catch (err: any) {
      console.error('Failed to create timetable version:', err);
    } finally {
      setIsCreatingVersion(false);
    }
  };

  // ── Print Handler ─────────────────────────────────────────────────────────
  const handlePrint = () => {
    window.print();
  };

  // ── Publish Timetable Handler ─────────────────────────────────────────────
  const handlePublishTimetable = async () => {
    if (!activeVersion?.id) return;
    setIsPublishing(true);
    setPublishSuccessMsg('');

    try {
      await apiClient.post(`/timetable/versions/${activeVersion.id}/publish/`);
      await queryClient.invalidateQueries({ queryKey: ['timetable-version', selectedClassId, selectedTermId] });
      refetchTimetable();
      setPublishSuccessMsg(
        `Timetable for ${classLabel} (${termLabel}) has been published! Parents can now send TIMETABLE to the WhatsApp bot to receive this schedule.`
      );
    } catch (err: any) {
      console.error('Failed to publish timetable version:', err);
      alert(parseApiError(err));
    } finally {
      setIsPublishing(false);
    }
  };

  const handleFetchWhatsAppPreview = async () => {
    if (!activeVersion?.id) return;
    try {
      const res = await apiClient.get(`/timetable/versions/${activeVersion.id}/whatsapp-preview/`);
      setWhatsAppPreviewText(res.data?.preview || 'No preview available.');
      setShowWhatsAppPreview(true);
    } catch (err: any) {
      alert(parseApiError(err));
    }
  };

  // ── Labels ────────────────────────────────────────────────────────────────
  const selectedClassObj = classes.find((c) => String(c.id) === selectedClassId);
  const selectedTermObj = terms.find((t) => String(t.id) === selectedTermId);
  const classLabel = selectedClassObj?.name || 'Selected Class';
  const termLabel = selectedTermObj?.name || 'Current Term';
  const schoolName = tenant?.name || 'School Name';

  const isLoading = classesLoading || termsLoading || timetableLoading;

  return (
    <div className="space-y-6">
      {/* ── Print-only Header (Hidden on Screen, Visible on Paper/PDF) ─────── */}
      <div className="hidden print:block mb-6 text-center border-b-2 border-slate-900 pb-4">
        <h1 className="text-xl font-black uppercase tracking-wider text-slate-900">{schoolName}</h1>
        <h2 className="text-base font-bold text-slate-800 mt-1">
          Master Class Timetable — {classLabel}
        </h2>
        <p className="text-xs text-slate-600 mt-0.5">
          Academic Term: {termLabel} · Effective From: {activeVersion?.effective_from || 'Current Term'} · Version {activeVersion?.version_number || 1}
        </p>
      </div>

      {/* ── Screen Header & Actions ─────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 print:hidden">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to="/academics" className="text-slate-400 hover:text-white transition-colors">
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Master Class Timetable
            </h1>
          </div>
          <p className="text-xs text-slate-400">
            Weekly lesson schedules, period breakdowns, and teacher assignments per class stream
          </p>
        </div>

        {/* ── Controls — Term + Class selectors + Print button ────────────── */}
        <div className="flex flex-wrap items-end gap-3">
          {/* Term selector */}
          <div className="space-y-1.5 min-w-[170px]">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-emerald-400" />
              Academic Term
            </label>
            <div className="relative">
              <select
                value={selectedTermId}
                onChange={(e) => setSelectedTermId(e.target.value)}
                className="w-full appearance-none bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2.5 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all cursor-pointer"
              >
                <option value="">
                  {termsLoading ? 'Loading terms…' : 'Select Term…'}
                </option>
                {terms.map((t) => (
                  <option key={t.id} value={String(t.id)}>
                    {t.name}{t.is_current ? ' (Current)' : ''}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            </div>
          </div>

          {/* Class stream selector */}
          <div className="space-y-1.5 min-w-[190px]">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
              Class Stream
            </label>
            <div className="relative">
              <select
                value={selectedClassId}
                onChange={(e) => setSelectedClassId(e.target.value)}
                className="w-full appearance-none bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2.5 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all cursor-pointer"
              >
                <option value="">
                  {classesLoading ? 'Loading classes…' : 'Select Class / Stream…'}
                </option>
                {primaryClasses.length > 0 && (
                  <optgroup label="─── Primary Level ───">
                    {primaryClasses.map((c) => (
                      <option key={c.id} value={String(c.id)}>{c.name}</option>
                    ))}
                  </optgroup>
                )}
                {oLevelClasses.length > 0 && (
                  <optgroup label="─── O-Level (S1–S4) ───">
                    {oLevelClasses.map((c) => (
                      <option key={c.id} value={String(c.id)}>{c.name}</option>
                    ))}
                  </optgroup>
                )}
                {aLevelClasses.length > 0 && (
                  <optgroup label="─── A-Level (S5–S6) ───">
                    {aLevelClasses.map((c) => (
                      <option key={c.id} value={String(c.id)}>{c.name}</option>
                    ))}
                  </optgroup>
                )}
                {otherClasses.length > 0 && (
                  <optgroup label="─── Other Classes ───">
                    {otherClasses.map((c) => (
                      <option key={c.id} value={String(c.id)}>{c.name}</option>
                    ))}
                  </optgroup>
                )}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            </div>
          </div>

          {/* WhatsApp Preview Button */}
          {activeVersion && (
            <button
              onClick={handleFetchWhatsAppPreview}
              className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm"
              title="Preview timetable format sent to parents on WhatsApp"
            >
              <MessageSquare className="w-4 h-4 text-emerald-400" />
              <span>WhatsApp Preview</span>
            </button>
          )}

          {/* Publish Timetable Button */}
          {activeVersion && (
            <button
              onClick={handlePublishTimetable}
              disabled={isPublishing}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm"
              title="Publish timetable and sync to WhatsApp for parents"
            >
              {isPublishing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Publishing…</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Publish Timetable</span>
                </>
              )}
            </button>
          )}

          {/* Print Button */}
          <button
            onClick={handlePrint}
            disabled={!activeVersion || uniqueTimeRows.length === 0}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            title="Print or export class timetable to PDF"
          >
            <Printer className="w-4 h-4 text-emerald-400" />
            <span>Print</span>
          </button>
        </div>
      </div>

      {/* ── Publish Success Notification Banner ─────────────────────────────── */}
      {publishSuccessMsg && (
        <div className="print:hidden bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-4 flex items-start justify-between gap-3 text-xs text-emerald-300 animate-in fade-in duration-200">
          <div className="flex items-start gap-2.5">
            <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-white mb-0.5">Timetable Published Successfully</p>
              <p>{publishSuccessMsg}</p>
            </div>
          </div>
          <button
            onClick={() => setPublishSuccessMsg('')}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ── Conflict Alert Banner (If Conflicts Exist) ──────────────────────── */}
      {conflicts.length > 0 && (
        <div className="print:hidden bg-amber-500/10 border border-amber-500/30 rounded-xl p-3.5 flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-amber-300">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>{conflicts.length} teacher double-booking conflict(s)</strong> detected in this timetable version.
            </span>
          </div>
          <button
            onClick={() => setShowConflictsModal(true)}
            className="text-amber-400 hover:text-amber-300 underline font-semibold shrink-0"
          >
            View Details
          </button>
        </div>
      )}

      {/* ── Timetable Grid Card ─────────────────────────────────────────────── */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl print:bg-white print:border print:border-slate-300 print:rounded-none print:shadow-none">
        {/* Card header — dynamic class + term name */}
        <div className="px-5 py-3.5 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 print:hidden">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-emerald-400 shrink-0" />
            <h2 className="text-sm font-bold text-white">
              {selectedClassId
                ? `Weekly Schedule for ${classLabel}`
                : 'Select a Class to View Schedule'}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            {selectedTermId && (
              <span className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                {termLabel} · Mon – Fri
              </span>
            )}
            {activeVersion && (
              <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-semibold flex items-center gap-1 ${
                activeVersion.is_active
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              }`}>
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                v{activeVersion.version_number} · {activeVersion.is_active ? 'Published' : 'Draft'}
              </span>
            )}
          </div>
        </div>

        {/* ── States ──────────────────────────────────────────────────────── */}
        {!selectedClassId || !selectedTermId ? (
          <div className="p-14 text-center">
            <BookOpen className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-sm font-semibold text-slate-300 mb-1">
              Select a Class Stream and Term
            </p>
            <p className="text-xs text-slate-500">
              The timetable grid will appear once both are selected above.
            </p>
          </div>
        ) : isLoading ? (
          <div className="p-14 text-center">
            <div className="w-8 h-8 border-2 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-xs text-slate-400">Loading timetable…</p>
          </div>
        ) : timetableError ? (
          <div className="p-12 text-center">
            <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
            <p className="text-sm font-semibold text-rose-300 mb-1">
              Failed to Load Timetable
            </p>
            <p className="text-xs text-slate-500">
              Check your connection or contact the system administrator.
            </p>
          </div>
        ) : !activeVersion ? (
          <div className="p-14 text-center space-y-4">
            <Calendar className="w-10 h-10 text-slate-600 mx-auto mb-1" />
            <div>
              <p className="text-sm font-semibold text-slate-300 mb-1">
                No Active Timetable for {classLabel}
              </p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                No timetable version has been published for{' '}
                <span className="text-slate-400 font-medium">{classLabel}</span> in{' '}
                <span className="text-slate-400 font-medium">{termLabel}</span>.
              </p>
            </div>
            <button
              onClick={handleCreateStarterTimetable}
              disabled={isCreatingVersion}
              className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow transition-all"
            >
              {isCreatingVersion ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Generating Schedule…
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Generate Timetable for {classLabel}
                </>
              )}
            </button>
          </div>
        ) : uniqueTimeRows.length === 0 ? (
          <div className="p-14 text-center">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
            <p className="text-sm font-semibold text-slate-300 mb-1">
              Timetable has No Slots Configured
            </p>
            <p className="text-xs text-slate-500">
              Version {activeVersion.version_number} exists but contains no periods yet.
            </p>
          </div>
        ) : (
          /* ── Timetable Grid ──────────────────────────────────────────── */
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[760px] print:min-w-full print:text-black">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/50 print:bg-slate-100 print:border-slate-300">
                  <th className="p-3 text-[11px] font-bold text-slate-400 uppercase tracking-wider w-28 print:text-black print:border print:border-slate-300">
                    Time / Day
                  </th>
                  {DAY_MAP.map((d) => (
                    <th
                      key={d.id}
                      className="p-3 text-[11px] font-bold text-slate-300 uppercase tracking-wider print:text-black print:border print:border-slate-300"
                    >
                      {d.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-xs print:divide-slate-300">
                {uniqueTimeRows.map((row) => {
                  const sampleSlot = slots.find((s) => s.start_time === row.start_time);
                  const isBreak = sampleSlot ? isBreakRow(sampleSlot) : false;

                  return (
                    <tr
                      key={row.start_time}
                      className={isBreak ? 'bg-slate-950/30 print:bg-slate-100' : 'hover:bg-slate-800/15 transition-colors print:hover:bg-transparent'}
                    >
                      {/* Time column */}
                      <td className="p-3 font-mono text-[11px] text-slate-400 whitespace-nowrap print:text-slate-900 print:border print:border-slate-300">
                        {fmtTime(row.start_time)} – {fmtTime(row.end_time)}
                      </td>

                      {isBreak ? (
                        /* Break / Lunch row spanning all 5 columns */
                        <td
                          colSpan={5}
                          className="p-3 text-center text-slate-400 font-semibold uppercase tracking-wider text-[11px] print:text-slate-900 print:border print:border-slate-300"
                        >
                          {sampleSlot ? breakLabel(sampleSlot) : 'Break'}
                        </td>
                      ) : (
                        /* Regular lesson slots */
                        DAY_MAP.map((d) => {
                          const slot = getSlot(d.id, row.start_time);
                          const isLesson = slot && slot.slot_type === 'lesson';
                          const isStudy = slot && slot.slot_type === 'study';
                          const badge = isLesson ? getSubjectBadgeStyle(slot.subject_display) : null;

                          return (
                            <td key={d.id} className="p-1.5 print:border print:border-slate-300">
                              {isLesson && badge ? (
                                <div
                                  onClick={() => openEditModal(slot)}
                                  className={`p-2.5 rounded-xl border transition-all cursor-pointer group ${badge.bg} ${badge.border} print:border-slate-300 print:bg-transparent`}
                                  title="Click to view or edit slot details"
                                >
                                  <div className="flex items-start justify-between gap-1">
                                    <div className="flex items-center gap-1.5 font-bold text-xs leading-tight">
                                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${badge.dot} print:bg-black`} />
                                      <span className={`${badge.text} print:text-black`}>{slot.subject_display}</span>
                                    </div>
                                    <Edit3 className="w-3 h-3 text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 print:hidden" />
                                  </div>
                                  {slot.teacher_name && (
                                    <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mt-1 print:text-slate-700">
                                      <User className="w-2.5 h-2.5 text-slate-500 shrink-0 print:hidden" />
                                      <span className="truncate">{slot.teacher_name}</span>
                                    </div>
                                  )}
                                  {slot.room && (
                                    <div className="text-[10px] text-slate-500 font-mono mt-0.5 print:text-slate-600">
                                      {slot.room}
                                    </div>
                                  )}
                                </div>
                              ) : isStudy ? (
                                <div
                                  onClick={() => openEditModal(slot)}
                                  className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-center cursor-pointer hover:border-indigo-500/40 transition-all print:border-slate-300"
                                >
                                  <span className="text-[11px] text-indigo-300 font-medium print:text-black">📖 Self Study</span>
                                  {slot.teacher_name && (
                                    <div className="text-[10px] text-indigo-400/80 truncate mt-0.5 print:text-slate-600">
                                      {slot.teacher_name}
                                    </div>
                                  )}
                                </div>
                              ) : slot ? (
                                <div
                                  onClick={() => openEditModal(slot)}
                                  className="p-2.5 rounded-xl border border-dashed border-slate-700 hover:border-emerald-500/50 hover:bg-slate-800/40 text-center text-[11px] text-slate-400 hover:text-emerald-300 cursor-pointer transition-all print:text-slate-400 print:border-slate-200"
                                  title="Click to configure slot"
                                >
                                  {slot.slot_type === 'break' ? '☕ Break' : slot.slot_type === 'lunch' ? '🍲 Lunch' : slot.slot_type === 'assembly' ? '📢 Assembly' : 'Free Period'}
                                </div>
                              ) : (
                                <div
                                  onClick={() => openCreateModal(d.id, d.label, row.period_number, row.start_time, row.end_time)}
                                  className="p-2.5 rounded-xl border border-dashed border-slate-800 hover:border-emerald-500/50 hover:bg-emerald-500/5 text-center text-[11px] text-slate-600 hover:text-emerald-400 cursor-pointer transition-all print:text-slate-400 print:border-slate-200"
                                  title="Click to add lesson slot"
                                >
                                  + Add Slot
                                </div>
                              )}
                            </td>
                          );
                        })
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Version Metadata Footer ─────────────────────────────────────────── */}
      {activeVersion && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-[11px] text-slate-500 print:hidden">
          <div className="flex items-center gap-3">
            <span>
              Class: <span className="text-slate-400 font-medium">{activeVersion.class_group_name}</span>
            </span>
            <span>·</span>
            <span>
              Term: <span className="text-slate-400 font-medium">{activeVersion.term_name}</span>
            </span>
            <span>·</span>
            <span>
              Version: <span className="text-slate-400 font-medium">v{activeVersion.version_number}</span>
            </span>
            <span>·</span>
            <span>
              Effective: <span className="text-slate-400 font-medium">{activeVersion.effective_from}</span>
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-slate-400">
            <Sparkles className="w-3 h-3 text-emerald-400" />
            <span>Click any period to modify subject or teacher assignment</span>
          </div>
        </div>
      )}

      {/* ── Slot Edit Modal ─────────────────────────────────────────────────── */}
      {editingSlot && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm print:hidden">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-emerald-400" />
                <h3 className="text-base font-bold text-white">
                  {editingSlot.id ? 'Edit Timetable Slot' : 'Add Timetable Slot'}
                </h3>
              </div>
              <button
                onClick={closeEditModal}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Time & Day Info */}
            <div className="bg-slate-800/60 rounded-xl p-3 text-xs flex items-center justify-between text-slate-300">
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Day & Period</span>
                <span className="font-bold text-white">{editingSlot.day_name} · Period {editingSlot.period_number}</span>
              </div>
              <div className="text-right">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Time Window</span>
                <span className="font-mono text-emerald-300">{editStartTime || fmtTime(editingSlot.start_time)} – {editEndTime || fmtTime(editingSlot.end_time)}</span>
              </div>
            </div>

            {saveSlotError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{saveSlotError}</span>
              </div>
            )}

            <div className="space-y-4 text-xs">
              {/* Start & End Time Inputs */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-semibold text-slate-300 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-emerald-400" />
                    Start Time
                  </label>
                  <input
                    type="time"
                    value={editStartTime}
                    onChange={(e) => setEditStartTime(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="font-semibold text-slate-300 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-emerald-400" />
                    End Time
                  </label>
                  <input
                    type="time"
                    value={editEndTime}
                    onChange={(e) => setEditEndTime(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
                    required
                  />
                </div>
              </div>

              {/* Slot Type */}
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Slot Type</label>
                <select
                  value={editSlotType}
                  onChange={(e) => setEditSlotType(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="lesson">Lesson (Subject teaching)</option>
                  <option value="study">Self Study</option>
                  <option value="break">Tea Break</option>
                  <option value="lunch">Lunch Break</option>
                  <option value="assembly">Assembly</option>
                </select>
              </div>

              {/* Subject (only if lesson) */}
              {editSlotType === 'lesson' && (
                <div className="space-y-1.5">
                  <label className="font-semibold text-slate-300">Subject</label>
                  <select
                    value={editSubjectId}
                    onChange={(e) => setEditSubjectId(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="">Select subject…</option>
                    {classSubjects.map((sub) => (
                      <option key={sub.id} value={String(sub.id)}>
                        {sub.name} {sub.code ? `(${sub.code})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Teacher (for lesson or study) */}
              {(editSlotType === 'lesson' || editSlotType === 'study') && (
                <div className="space-y-1.5">
                  <label className="font-semibold text-slate-300">Teacher Assigned</label>
                  <select
                    value={editTeacherId}
                    onChange={(e) => setEditTeacherId(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="">No teacher assigned (TBA)</option>
                    {staffList.map((staff) => (
                      <option key={staff.id} value={String(staff.id)}>
                        {staff.full_name} ({staff.role})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Room */}
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Room / Location</label>
                <input
                  type="text"
                  value={editRoom}
                  onChange={(e) => setEditRoom(e.target.value)}
                  placeholder="e.g. Room S5 Sci, Lab 1, Main Hall"
                  className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={closeEditModal}
                disabled={isSavingSlot}
                className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveSlot}
                disabled={isSavingSlot}
                className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-xl text-xs font-semibold transition-all shadow"
              >
                {isSavingSlot ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Saving…
                  </>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    Save Slot
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Conflicts Detail Modal ──────────────────────────────────────────── */}
      {showConflictsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm print:hidden">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <h3 className="text-base font-bold text-white">
                  Teacher Double-Booking Conflicts
                </h3>
              </div>
              <button
                onClick={() => setShowConflictsModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400">
              The following teachers are scheduled in multiple classrooms at the exact same time:
            </p>

            <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
              {conflicts.map((c, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-amber-300">{c.teacher}</span>
                    <span className="font-mono text-[10px] text-slate-400">{c.day} · {c.time}</span>
                  </div>
                  <div className="text-[11px] text-slate-300">
                    Conflict between <span className="font-semibold text-white">{c.class_1}</span> ({c.subject_1}) and{' '}
                    <span className="font-semibold text-white">{c.class_2}</span> ({c.subject_2})
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-2 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setShowConflictsModal(false)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold px-4 py-2 rounded-xl transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── WhatsApp Message Preview Modal ──────────────────────────────────── */}
      {showWhatsAppPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm print:hidden">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-emerald-400" />
                <h3 className="text-base font-bold text-white">
                  WhatsApp Timetable Message Preview
                </h3>
              </div>
              <button
                onClick={() => setShowWhatsAppPreview(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400">
              This is the exact message text that parents receive when texting <span className="text-emerald-400 font-mono font-bold">TIMETABLE</span> to the school WhatsApp number:
            </p>

            <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs font-mono text-emerald-300 whitespace-pre-wrap max-h-80 overflow-y-auto">
              {whatsAppPreviewText}
            </pre>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowWhatsAppPreview(false)}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-xl text-xs font-semibold"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
