import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { StatGroup } from '../../components/dashboard/StatGroup';
import { KpiCard } from '../../components/dashboard/KpiCard';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import {
  Users,
  CalendarCheck,
  GraduationCap,
  Clock,
  UserX,
  CalendarDays,
  MessageCircle,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  MapPin,
  Sparkles,
  Info,
  BookOpen,
  Loader2
} from 'lucide-react';

// ── TypeScript Interfaces for Backend API ────────────────────────────────────

interface TodayScheduleSlot {
  id: string;
  period_number: number;
  start_time: string;
  end_time: string;
  subject_name: string;
  class_group_id: number | null;
  class_group_name: string;
  room: string;
  slot_type: string;
}

interface AssignedClassAttendance {
  is_marked: boolean;
  present_count: number;
  late_count: number;
  absent_count: number;
  excused_count: number;
  total_marked: number;
  attendance_rate: number | null;
}

interface AssignedClass {
  id: number;
  name: string;
  level: string;
  stream: string;
  student_count: number;
  attendance_today: AssignedClassAttendance;
}

interface TeachingClass {
  id: number;
  name: string;
  level: string;
  stream: string;
  student_count: number;
}

interface AbsentStudent {
  student_id: string;
  student_name: string;
  reg_number: string;
  class_group_name: string;
  guardian_name: string;
  guardian_phone: string;
  pre_excused: boolean;
  notes: string;
}

interface PendingAssessmentMark {
  assessment_id: string;
  name: string;
  assessment_type: string;
  class_group_id: number;
  class_group_name: string;
  subject_id: number | null;
  subject_name: string;
  max_marks: number;
  status: string;
  is_locked: boolean;
  marks_entered_count: number;
  total_students_count: number;
  completion_pct: number;
}

interface TeacherDashboardData {
  teacher: {
    id: string;
    name: string;
    email: string;
    role: string;
    phone: string;
  };
  school: {
    id: number | string;
    name: string;
  };
  current_term: {
    id: number | string;
    name: string;
    academic_year: number | null;
    term_number: number;
    start_date: string;
    end_date: string;
  } | null;
  today_date: string;
  today_day_name: string;
  kpis: {
    assigned_classes_count: number;
    total_students_count: number;
    today_lessons_count: number;
    absent_students_today_count: number;
    pending_assessments_count: number;
  };
  schedule_day?: {
    id: number;
    name: string;
    short: string;
    is_today: boolean;
    is_weekend_fallback: boolean;
    available_days: Array<{ id: number; name: string; short: string }>;
  };
  primary_form_class?: {
    id: number;
    name: string;
    level: string;
    stream: string;
  } | null;
  today_schedule: TodayScheduleSlot[];
  assigned_classes: AssignedClass[];
  teaching_classes?: TeachingClass[];
  absent_students_today: AbsentStudent[];
  pending_marks: PendingAssessmentMark[];
}

export const TeacherDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedDay, setSelectedDay] = useState<number | null>(null);

  // Smooth scroll helper for interactive KPI cards
  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Query dynamic data from backend Teacher Dashboard API
  const { data, isLoading, isFetching, error } = useQuery<TeacherDashboardData>({
    queryKey: ['teacher-dashboard', selectedDay],
    queryFn: async () => {
      const url = selectedDay !== null
        ? `/automation/teacher-dashboard/?day_of_week=${selectedDay}`
        : '/automation/teacher-dashboard/';
      const res = await apiClient.get(url);
      return res.data;
    },
    placeholderData: (previousData) => previousData,
    refetchInterval: 1000 * 60 * 2, // 2 minutes live refresh
  });

  const teacher = data?.teacher;
  const school = data?.school;
  const term = data?.current_term;
  const kpis = data?.kpis;
  const scheduleDay = data?.schedule_day;
  const todaySchedule = data?.today_schedule || [];
  const assignedClasses = data?.assigned_classes || [];
  const teachingClasses = data?.teaching_classes || [];
  const absentStudents = data?.absent_students_today || [];
  const pendingMarks = data?.pending_marks || [];

  // Active day index (either selected by user or backend default)
  const currentDayId = selectedDay !== null ? selectedDay : (scheduleDay?.id ?? 0);

  // Format today's date for display (e.g. 04 September 2026)
  const formattedDate = React.useMemo(() => {
    if (!data?.today_date) return '';
    try {
      const d = new Date(data.today_date);
      return d.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return data.today_date;
    }
  }, [data?.today_date]);

  // Clean phone number for WhatsApp wa.me links
  const formatWhatsAppUrl = (phone: string, studentName: string) => {
    if (!phone) return null;
    const cleanPhone = phone.replace(/[^0-9]/g, '');
    const fullPhone = cleanPhone.startsWith('0') ? `256${cleanPhone.slice(1)}` : cleanPhone;
    const message = encodeURIComponent(
      `Hello, this is ${teacher?.name || 'Teacher'} from ${school?.name || 'School'}. I am reaching out regarding ${studentName}'s attendance today.`
    );
    return `https://wa.me/${fullPhone}?text=${message}`;
  };

  // Primary class for Quick Attendance button (Ruth's P.5 East is ID 46)
  const primaryClassId = data?.primary_form_class?.id || assignedClasses[0]?.id;

  if (error) {
    return (
      <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-6 text-center text-rose-300">
        <AlertCircle className="w-8 h-8 mx-auto mb-2 text-rose-400" />
        <h2 className="text-lg font-bold">Unable to load Teacher Dashboard</h2>
        <p className="text-sm text-slate-400 mt-1">
          Please check your network connection or contact the school administrator.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Top Header Bar ──────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 bg-gradient-to-r from-slate-800/90 via-slate-800/60 to-slate-900 border border-slate-700/60 rounded-2xl p-6 shadow-xl backdrop-blur-md">
        <div>
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles className="w-3 h-3" />
              Teacher Workspace
            </span>
            {term && (
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                {term.name}
              </span>
            )}
            <span className="text-xs text-slate-400">
              {data?.today_day_name && `${data.today_day_name}, `}{formattedDate}
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Welcome, {teacher?.name || 'Teacher'}
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            {school?.name ? `${school.name} • ` : ''}
            {data?.primary_form_class
              ? `Form Teacher of ${data.primary_form_class.name}`
              : 'Real-time lesson schedules, attendance registers, and marks entry'}
          </p>
        </div>

        {/* Quick Action Buttons */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Prominent Quick Mark Attendance button required by Test 3.1 */}
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              if (primaryClassId) {
                navigate(`/attendance?class_id=${primaryClassId}&date=${data?.today_date || ''}`);
              } else {
                navigate('/attendance');
              }
            }}
            className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-lg shadow-emerald-900/30 ring-1 ring-emerald-400/40"
            leftIcon={<CalendarCheck className="w-4 h-4 text-white" />}
          >
            Quick Mark Attendance
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/academics')}
            leftIcon={<GraduationCap className="w-4 h-4 text-amber-400" />}
          >
            Enter Marks
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/academics/timetable')}
            leftIcon={<CalendarDays className="w-4 h-4 text-indigo-400" />}
          >
            Full Timetable
          </Button>
        </div>
      </div>

      {/* ── Interactive KPI Stat Group ─────────────────────────────────── */}
      <StatGroup>
        <KpiCard
          title="My Classes (Form Class)"
          value={kpis?.assigned_classes_count != null ? kpis.assigned_classes_count : '—'}
          change={kpis?.total_students_count != null ? `${kpis.total_students_count} students` : ''}
          changeType="neutral"
          subtitle={data?.primary_form_class ? data.primary_form_class.name : "Assigned pastoral class"}
          icon={<Users className="w-5 h-5 text-indigo-400" />}
          isLoading={isLoading}
          onClick={() => scrollToSection('my-classes-section')}
          clickableHint="View classes"
        />

        <KpiCard
          title="Today's Timetable"
          value={kpis?.today_lessons_count != null ? `${kpis.today_lessons_count} Periods` : '—'}
          change={scheduleDay?.name || data?.today_day_name || ''}
          changeType="positive"
          subtitle={scheduleDay?.is_weekend_fallback ? "Monday schedule" : "Scheduled lessons"}
          icon={<Clock className="w-5 h-5 text-emerald-400" />}
          isLoading={isLoading}
          onClick={() => scrollToSection('timetable-section')}
          clickableHint="View schedule"
        />

        <KpiCard
          title="Absent Students Today"
          value={kpis?.absent_students_today_count != null ? kpis.absent_students_today_count : '—'}
          change={kpis?.absent_students_today_count ? 'Follow-up required' : 'Full attendance'}
          changeType={kpis?.absent_students_today_count ? 'negative' : 'positive'}
          subtitle="In your form classes today"
          icon={<UserX className="w-5 h-5 text-rose-400" />}
          isLoading={isLoading}
          onClick={() => scrollToSection('absent-students-section')}
          clickableHint="View roster"
        />

        <KpiCard
          title="Pending Marks / Drafts"
          value={kpis?.pending_assessments_count != null ? kpis.pending_assessments_count : '—'}
          change={kpis?.pending_assessments_count ? 'Action pending' : 'Up to date'}
          changeType={kpis?.pending_assessments_count ? 'negative' : 'positive'}
          subtitle="Assessments requiring entry"
          icon={<ClipboardList className="w-5 h-5 text-amber-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/academics')}
          clickableHint="Open marks"
        />
      </StatGroup>

      {/* ── Main Two-Column Layout ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left 2 Columns: Timetable & "My Classes" Section */}
        <div className="xl:col-span-2 space-y-6">

          {/* 1. Today's Timetable Schedule (with Day Selector & Weekend Fallback) */}
          <div id="timetable-section" className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl scroll-mt-20">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div>
                <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                  <Clock className="w-4 h-4 text-emerald-400" />
                  Today&apos;s Timetable ({scheduleDay?.name || data?.today_day_name || 'Lessons'})
                  {isFetching && !isLoading && (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400 ml-1" />
                  )}
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Chronological periods for your teaching schedule
                </p>
              </div>

              {/* Day Selector Pills */}
              <div className="flex items-center gap-1 bg-slate-900/80 border border-slate-700/80 rounded-xl p-1 self-start sm:self-auto">
                {(scheduleDay?.available_days || [
                  { id: 0, name: 'Monday', short: 'Mon' },
                  { id: 1, name: 'Tuesday', short: 'Tue' },
                  { id: 2, name: 'Wednesday', short: 'Wed' },
                  { id: 3, name: 'Thursday', short: 'Thu' },
                  { id: 4, name: 'Friday', short: 'Fri' },
                ]).map((d) => {
                  const isActive = currentDayId === d.id;
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setSelectedDay(d.id)}
                      className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all ${
                        isActive
                          ? 'bg-emerald-500 text-slate-950 shadow-sm shadow-emerald-500/20 font-bold'
                          : 'text-slate-400 hover:text-white hover:bg-slate-800'
                      }`}
                      title={`View ${d.name}'s schedule`}
                    >
                      {d.short}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Weekend Notice Fallback Banner */}
            {scheduleDay?.is_weekend_fallback && (
              <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-3 mb-4 flex items-start gap-2.5 text-xs text-indigo-300">
                <Info className="w-4 h-4 shrink-0 text-indigo-400 mt-0.5" />
                <div>
                  <span className="font-semibold text-indigo-200">Weekend Schedule View:</span>{' '}
                  School is closed on weekends. Displaying upcoming <b>Monday</b> schedule. Click any day above to inspect lessons for that day.
                </div>
              </div>
            )}

            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="h-16 bg-slate-700/40 rounded-xl animate-pulse" />
                ))}
              </div>
            ) : todaySchedule.length === 0 ? (
              <div className="text-center py-10 border border-dashed border-slate-700 rounded-xl bg-slate-800/40">
                <CalendarDays className="w-10 h-10 mx-auto text-slate-500 mb-2" />
                <h3 className="text-sm font-medium text-slate-300">
                  No lessons scheduled for {scheduleDay?.name || 'this day'}
                </h3>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  There are no periods assigned to your timetable for this day. Use this time for grading or lesson preparation.
                </p>
              </div>
            ) : (
              <div className={`divide-y divide-slate-700/50 transition-opacity duration-200 ${isFetching && !isLoading ? 'opacity-50' : 'opacity-100'}`}>
                {todaySchedule.map((slot) => (
                  <div
                    key={slot.id}
                    className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-700/20 px-3 rounded-xl transition-colors"
                  >
                    <div className="flex items-start sm:items-center gap-3">
                      {/* Period Badge */}
                      <div className="w-11 h-11 rounded-xl bg-slate-900 border border-slate-700/80 flex flex-col items-center justify-center shrink-0">
                        <span className="text-[10px] uppercase font-bold text-slate-400 leading-none">Period</span>
                        <span className="text-sm font-extrabold text-emerald-400 leading-tight">{slot.period_number}</span>
                      </div>

                      {/* Details */}
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-white">
                            {slot.subject_name}
                          </span>
                          <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                            {slot.class_group_name}
                          </span>
                          {slot.room && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
                              <MapPin className="w-3 h-3 text-slate-500" />
                              {slot.room}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                          <Clock className="w-3 h-3 text-slate-500" />
                          <span>{slot.start_time} – {slot.end_time}</span>
                          <span className="text-slate-600">•</span>
                          <span className="capitalize text-slate-400">{slot.slot_type}</span>
                        </div>
                      </div>
                    </div>

                    {/* Action Shortcut */}
                    <div className="flex items-center gap-2 self-end sm:self-center">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => navigate(`/attendance?class_id=${slot.class_group_id}&date=${data?.today_date || ''}`)}
                        className="text-xs h-8 px-2.5"
                      >
                        Register
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate('/academics')}
                        className="text-xs h-8 px-2.5 text-slate-400 hover:text-white"
                      >
                        Marks
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 2. "My Classes" Section (Specified in Test 3.1: My Classes section - P.5 East) */}
          <div id="my-classes-section" className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl scroll-mt-20">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                  <Users className="w-4 h-4 text-teal-400" />
                  My Classes
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Your assigned form class and pastoral care groups
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (primaryClassId) {
                    navigate(`/attendance?class_id=${primaryClassId}&date=${data?.today_date || ''}`);
                  } else {
                    navigate('/attendance');
                  }
                }}
                rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
              >
                Open Register
              </Button>
            </div>

            {isLoading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[1, 2].map((n) => (
                  <div key={n} className="h-32 bg-slate-700/40 rounded-xl animate-pulse" />
                ))}
              </div>
            ) : assignedClasses.length === 0 ? (
              <div className="text-center py-8 border border-dashed border-slate-700 rounded-xl bg-slate-800/40">
                <Users className="w-8 h-8 mx-auto text-slate-500 mb-2" />
                <p className="text-xs text-slate-400">No form classes assigned to your profile.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {assignedClasses.map((cls) => {
                  const att = cls.attendance_today;
                  return (
                    <div
                      key={cls.id}
                      className="bg-slate-900/80 border border-slate-700/80 rounded-xl p-4.5 hover:border-emerald-500/40 transition-all flex flex-col justify-between shadow-lg relative overflow-hidden"
                    >
                      {/* Top ribbon for Form Class */}
                      <div className="absolute top-0 right-0 w-24 h-1 bg-gradient-to-r from-emerald-500 to-teal-400" />

                      <div>
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-base font-bold text-white">{cls.name}</h3>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 uppercase tracking-wide">
                                Form Class
                              </span>
                            </div>
                            <p className="text-xs text-slate-400 mt-1">
                              {cls.student_count} Enrolled Student{cls.student_count === 1 ? '' : 's'}
                            </p>
                          </div>

                          {att.is_marked ? (
                            <Badge variant="success" size="sm">
                              Marked
                            </Badge>
                          ) : (
                            <Badge variant="warning" size="sm">
                              Pending Today
                            </Badge>
                          )}
                        </div>

                        {/* Attendance Breakdown */}
                        {att.is_marked ? (
                          <div className="space-y-1.5 mt-3 bg-slate-800/50 p-3 rounded-lg border border-slate-700/50">
                            <div className="flex items-center justify-between text-xs text-slate-300">
                              <span className="text-slate-400 font-medium">Today&apos;s Attendance</span>
                              <span className="font-bold text-emerald-400">
                                {att.attendance_rate != null ? `${att.attendance_rate}%` : '—'}
                              </span>
                            </div>
                            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden flex">
                              <div
                                style={{ width: `${att.attendance_rate || 0}%` }}
                                className="bg-emerald-500 h-full rounded-full"
                              />
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                              <span>Present: <b className="text-emerald-400">{att.present_count}</b></span>
                              <span>Late: <b className="text-amber-300">{att.late_count}</b></span>
                              <span>Absent: <b className="text-rose-400">{att.absent_count}</b></span>
                              <span>Excused: <b className="text-sky-300">{att.excused_count}</b></span>
                            </div>
                          </div>
                        ) : (
                          <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 mt-3 text-xs text-amber-300 flex items-center gap-2.5">
                            <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
                            <span>Today&apos;s morning register has not yet been marked.</span>
                          </div>
                        )}
                      </div>

                      <div className="pt-4 mt-3 border-t border-slate-800/80 flex items-center justify-between gap-2">
                        <span className="text-xs text-slate-400">Form Teacher: <b className="text-slate-300">{teacher?.name || 'You'}</b></span>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => navigate(`/attendance?class_id=${cls.id}&date=${data?.today_date || ''}`)}
                          className="text-xs h-8 px-3 bg-emerald-600 hover:bg-emerald-500 text-white font-medium"
                          rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
                        >
                          {att.is_marked ? 'Review Register' : 'Quick Mark Register'}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Additional Teaching Classes (if any from timetable) */}
            {teachingClasses.length > 0 && (
              <div className="mt-6 pt-4 border-t border-slate-700/60">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                  Other Classes You Teach
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                  {teachingClasses.map((tcls) => (
                    <div
                      key={tcls.id}
                      className="bg-slate-900/60 border border-slate-700/60 rounded-xl p-3 flex items-center justify-between"
                    >
                      <div>
                        <div className="text-xs font-bold text-white">{tcls.name}</div>
                        <div className="text-[11px] text-slate-400">{tcls.student_count} students</div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate(`/attendance?class_id=${tcls.id}&date=${data?.today_date || ''}`)}
                        className="text-xs h-7 px-2 text-indigo-400 hover:text-white"
                      >
                        Register
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Column: Absent Students Alert & Marks Queue */}
        <div className="space-y-6">

          {/* 3. Today's Absent Students Alert Roster (Specified in Test 3.1) */}
          <div id="absent-students-section" className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl scroll-mt-20">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                  <UserX className="w-4 h-4 text-rose-400" />
                  Absent Students Today
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Unexcused and recorded absences in your form classes
                </p>
              </div>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                absentStudents.length > 0
                  ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                  : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
              }`}>
                {absentStudents.length}
              </span>
            </div>

            {isLoading ? (
              <div className="space-y-3">
                {[1, 2].map((n) => (
                  <div key={n} className="h-14 bg-slate-700/40 rounded-xl animate-pulse" />
                ))}
              </div>
            ) : absentStudents.length === 0 ? (
              <div className="text-center py-8 border border-slate-700/50 rounded-xl bg-emerald-500/5 border-dashed">
                <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400 mb-2" />
                <h3 className="text-xs font-semibold text-emerald-300">All students present today</h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  No unexcused absences recorded across your assigned classes today.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {absentStudents.map((st) => {
                  const waUrl = formatWhatsAppUrl(st.guardian_phone, st.student_name);
                  return (
                    <div
                      key={st.student_id}
                      className="bg-slate-900/60 border border-slate-700/60 rounded-xl p-3 hover:border-slate-600 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h4 className="text-xs font-bold text-white">{st.student_name}</h4>
                          <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mt-0.5">
                            <span className="font-mono text-slate-300">{st.reg_number}</span>
                            <span>•</span>
                            <span className="text-indigo-300 font-medium">{st.class_group_name}</span>
                          </div>
                        </div>

                        {st.pre_excused ? (
                          <Badge variant="info" size="sm">
                            Notified
                          </Badge>
                        ) : (
                          <Badge variant="danger" size="sm">
                            Absent
                          </Badge>
                        )}
                      </div>

                      {/* Guardian & Reason */}
                      <div className="mt-2.5 pt-2 border-t border-slate-800 flex items-center justify-between gap-2 text-[11px]">
                        <div className="truncate text-slate-400">
                          <span className="text-slate-500">Guardian: </span>
                          <span className="text-slate-300">{st.guardian_name}</span>
                          {st.notes && <p className="text-[10px] text-amber-300/80 truncate mt-0.5">{st.notes}</p>}
                        </div>

                        {/* WhatsApp Parent Contact Link */}
                        {waUrl && (
                          <a
                            href={waUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 transition-colors shrink-0 text-[10px] font-semibold"
                            title="Message parent on WhatsApp"
                          >
                            <MessageCircle className="w-3 h-3" />
                            <span>WhatsApp</span>
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 4. Pending Marks & Assessment Queue */}
          <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                  <GraduationCap className="w-4 h-4 text-amber-400" />
                  Marks Entry Queue
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Draft and pending assessment submissions
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/academics')}
                className="text-xs h-7 text-amber-400 p-0 hover:text-amber-300"
              >
                View Grid
              </Button>
            </div>

            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="h-16 bg-slate-700/40 rounded-xl animate-pulse" />
                ))}
              </div>
            ) : pendingMarks.length === 0 ? (
              <div className="text-center py-8 border border-dashed border-slate-700 rounded-xl bg-slate-800/40">
                <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400 mb-2" />
                <h3 className="text-xs font-semibold text-slate-300">All marks submitted</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  There are no pending marks or unsubmitted assessments at this time.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {pendingMarks.slice(0, 6).map((item) => (
                  <div
                    key={item.assessment_id}
                    className="bg-slate-900/60 border border-slate-700/60 rounded-xl p-3 hover:border-slate-600 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="text-xs font-bold text-white leading-snug">{item.name}</h4>
                        <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mt-0.5">
                          <span className="text-indigo-300 font-semibold">{item.subject_name}</span>
                          <span>•</span>
                          <span className="text-slate-300">{item.class_group_name}</span>
                        </div>
                      </div>

                      <Badge
                        variant={
                          item.status === 'submitted'
                            ? 'info'
                            : item.status === 'approved'
                            ? 'success'
                            : 'warning'
                        }
                        size="sm"
                      >
                        {item.status}
                      </Badge>
                    </div>

                    {/* Progress Bar */}
                    <div className="mt-2.5">
                      <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                        <span>
                          {item.marks_entered_count} of {item.total_students_count} Marks Entered
                        </span>
                        <span className="font-semibold text-white">{item.completion_pct}%</span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          style={{ width: `${item.completion_pct}%` }}
                          className="bg-amber-400 h-full rounded-full transition-all"
                        />
                      </div>
                    </div>

                    <div className="mt-2 pt-2 border-t border-slate-800/80 flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate('/academics')}
                        className="text-[11px] h-6 px-2 text-emerald-400 hover:text-emerald-300"
                        rightIcon={<ChevronRight className="w-3 h-3" />}
                      >
                        Enter Marks
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
};

export default TeacherDashboardPage;
