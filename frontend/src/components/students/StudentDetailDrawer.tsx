import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Drawer } from '../ui/Drawer';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { Select } from '../ui/Select';
import { TextInput } from '../ui/TextInput';
import { RbacGate } from '../auth/RbacGate';
import { useRbac } from '../../hooks/useRbac';
import { 
  User, 
  Phone, 
  GraduationCap,
  Users,
  Banknote,
  Calendar,
  Hash,
  UserMinus,
  UserCheck,
  ShieldAlert,
  ClipboardCheck,
  Edit3
} from 'lucide-react';

interface StudentDetailDrawerProps {
  studentId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

interface Guardian {
  id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  phone: string;
  is_primary: boolean;
  preferred_language: string;
}

interface StudentDetail {
  id: string;
  student_id: string;
  admission_number?: string;
  full_name?: string;
  first_name: string;
  last_name: string;
  other_names?: string;
  date_of_birth: string;
  gender: string;
  current_class?: number | string | { id: string | number; name: string };
  class_name?: string;
  current_class_name?: string;
  admission_date: string;
  is_active: boolean;
  deactivated_at?: string;
  deactivation_reason?: string;
  guardians: Guardian[];
  fee_balance?: number;
  total_fees?: number;
}

const DEACTIVATION_REASONS = [
  { value: 'Transferred to another school', label: 'Transferred to another school' },
  { value: 'Graduated / Completed level', label: 'Graduated / Completed level' },
  { value: 'Withdrawn by parent/guardian', label: 'Withdrawn by parent/guardian' },
  { value: 'Disciplinary / Dismissed', label: 'Disciplinary / Dismissed' },
  { value: 'Financial constraints / Relocated', label: 'Financial constraints / Relocated' },
  { value: 'Other', label: 'Other (specify below)' },
];

export const StudentDetailDrawer: React.FC<StudentDetailDrawerProps> = ({
  studentId,
  isOpen,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const { can } = useRbac();
  const canViewFinance = can('view:finance');
  const canDeleteStudent = can('student:delete');
  const canEditStudent = can('student:edit');

  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [selectedReason, setSelectedReason] = useState('Transferred to another school');
  const [customReason, setCustomReason] = useState('');
  const [isSubmittingDeactivate, setIsSubmittingDeactivate] = useState(false);
  const [isReactivating, setIsReactivating] = useState(false);
  const [actionError, setActionError] = useState('');

  // Edit Student State
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    first_name: '',
    last_name: '',
    other_names: '',
    gender: '',
    date_of_birth: '',
    current_class: '',
  });
  const [isSubmittingEdit, setIsSubmittingEdit] = useState(false);
  const [editError, setEditError] = useState('');

  const { data: student, isLoading, refetch } = useQuery({
    queryKey: ['student-detail', studentId],
    queryFn: async () => {
      const res = await apiClient.get(`/students/${studentId}/`);
      return res.data as StudentDetail;
    },
    enabled: !!studentId && isOpen,
    staleTime: 0,
    refetchOnMount: 'always',
  });

  // Test 4.5: Dynamic Attendance Record queries
  const { data: attendanceSummary, isLoading: isLoadingAttendance } = useQuery({
    queryKey: ['attendance-summary-student', studentId],
    queryFn: async () => {
      const res = await apiClient.get('/attendance/summary/', {
        params: { student_id: studentId },
      });
      return res.data as {
        student_id: string;
        student_name: string;
        attendance_rate: number | null;
        below_threshold: boolean;
      };
    },
    enabled: !!studentId && isOpen,
    staleTime: 0,
  });

  const { data: attendanceRecords } = useQuery({
    queryKey: ['attendance-records-student', studentId],
    queryFn: async () => {
      const res = await apiClient.get('/attendance/records/', {
        params: { student_id: studentId, ordering: '-date' },
      });
      return (res.data?.results || res.data || []) as any[];
    },
    enabled: !!studentId && isOpen,
    staleTime: 0,
  });

  const { data: classData } = useQuery({
    queryKey: ['class-groups'],
    queryFn: async () => {
      const res = await apiClient.get('/students/classes/');
      return res.data?.results || res.data || [];
    },
    enabled: isOpen && canEditStudent,
  });

  const openEditModal = () => {
    if (!student) return;
    const currentClassId = typeof student.current_class === 'object' && student.current_class !== null
      ? String((student.current_class as any).id)
      : student.current_class ? String(student.current_class) : '';
    setEditForm({
      first_name: student.first_name || '',
      last_name: student.last_name || '',
      other_names: student.other_names || '',
      gender: student.gender || 'M',
      date_of_birth: student.date_of_birth || '',
      current_class: currentClassId,
    });
    setEditError('');
    setEditModalOpen(true);
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!studentId) return;
    setIsSubmittingEdit(true);
    setEditError('');
    try {
      await apiClient.patch(`/students/${studentId}/`, {
        first_name: editForm.first_name.trim(),
        last_name: editForm.last_name.trim(),
        other_names: editForm.other_names ? editForm.other_names.trim() : '',
        gender: editForm.gender,
        date_of_birth: editForm.date_of_birth || null,
        current_class: editForm.current_class ? Number(editForm.current_class) : null,
      });
      await refetch();
      queryClient.invalidateQueries({ queryKey: ['students'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail', studentId] });
      setEditModalOpen(false);
    } catch (err: any) {
      setEditError(err.response?.data?.detail || err.response?.data?.message || 'Failed to update student.');
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  const handleDeactivate = async () => {
    if (!studentId) return;
    setIsSubmittingDeactivate(true);
    setActionError('');
    try {
      const reason = selectedReason === 'Other' ? (customReason.trim() || 'Deactivated by Director') : selectedReason;
      await apiClient.delete(`/students/${studentId}/`, {
        data: { reason }
      });
      await refetch();
      queryClient.invalidateQueries({ queryKey: ['students'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail', studentId] });
      setDeactivateModalOpen(false);
      setCustomReason('');
    } catch (err: any) {
      setActionError(err.response?.data?.message || err.response?.data?.detail || 'Failed to deactivate student.');
    } finally {
      setIsSubmittingDeactivate(false);
    }
  };

  const handleReactivate = async () => {
    if (!studentId) return;
    setIsReactivating(true);
    setActionError('');
    try {
      await apiClient.post(`/students/${studentId}/reactivate/`);
      await refetch();
      queryClient.invalidateQueries({ queryKey: ['students'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail', studentId] });
    } catch (err: any) {
      try {
        await apiClient.patch(`/students/${studentId}/`, {
          is_active: true
        });
        await refetch();
        queryClient.invalidateQueries({ queryKey: ['students'] });
        queryClient.invalidateQueries({ queryKey: ['student-detail'] });
        queryClient.invalidateQueries({ queryKey: ['student-detail', studentId] });
      } catch (patchErr: any) {
        setActionError(patchErr.response?.data?.message || patchErr.response?.data?.detail || 'Failed to reactivate student.');
      }
    } finally {
      setIsReactivating(false);
    }
  };

  const fullName = student?.full_name || (student
    ? `${student.first_name} ${student.other_names ? student.other_names + ' ' : ''}${student.last_name}`.trim()
    : '');

  const className =
    student?.class_name ||
    student?.current_class_name ||
    (typeof student?.current_class === 'object' && student?.current_class !== null
      ? (student.current_class as any).name
      : null) ||
    'Not Assigned';

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title="Student Profile"
      description={canViewFinance ? "Full profile, guardian relationships, and fee status" : "Full profile and guardian relationships"}
    >
      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-20 bg-slate-800 rounded-xl" />
          <div className="h-12 bg-slate-800 rounded-xl" />
          <div className="h-36 bg-slate-800 rounded-xl" />
        </div>
      )}

      {student && (
        <div className="space-y-6">
          {/* Student Identity Card */}
          <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-500 flex items-center justify-center text-white font-bold text-lg shadow-lg">
                  {student.first_name[0]}{student.last_name[0]}
                </div>
                <div>
                  <h4 className="font-bold text-white text-base">{fullName}</h4>
                  <p className="text-xs text-emerald-400 font-semibold font-mono">
                    Admission No: {student.admission_number || student.student_id}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {canEditStudent && (
                  <button
                    type="button"
                    onClick={openEditModal}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white bg-slate-700/50 hover:bg-slate-700 transition-colors"
                    title="Edit student profile"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>
                )}
                <Badge variant={student.is_active ? 'success' : 'neutral'}>
                  {student.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-1">
              <InfoRow icon={<Hash className="w-3.5 h-3.5" />} label="Admission No." value={student.admission_number || student.student_id} />
              <InfoRow icon={<GraduationCap className="w-3.5 h-3.5" />} label="Class" value={className} />
              <InfoRow icon={<User className="w-3.5 h-3.5" />} label="Gender" value={student.gender === 'M' ? 'Male' : 'Female'} />
              <InfoRow icon={<Calendar className="w-3.5 h-3.5" />} label="Admitted" value={student.admission_date} />
            </div>
          </div>

          {/* Fee Status — Director & Bursar Only */}
          <RbacGate permission="view:finance" fallback={null}>
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 space-y-3">
              <h5 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Fee Status & Balance</h5>
              {student.fee_balance !== undefined && student.fee_balance !== null ? (
                <>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-slate-300">
                      <Banknote className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs">Outstanding Balance</span>
                    </div>
                    <span className={`text-sm font-bold font-mono ${Number(student.fee_balance) < 0 ? 'text-emerald-400' : Number(student.fee_balance) === 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {Number(student.fee_balance) < 0
                        ? `Credit: UGX ${Math.abs(Number(student.fee_balance)).toLocaleString()}`
                        : Number(student.fee_balance) === 0
                        ? 'UGX 0 (Cleared)'
                        : `UGX ${Number(student.fee_balance).toLocaleString()}`}
                    </span>
                  </div>
                  {Number(student.fee_balance) < 0 && (
                    <Badge variant="success">In Credit (Overpaid)</Badge>
                  )}
                  {Number(student.fee_balance) === 0 && (
                    <Badge variant="success">Fully Paid / Cleared</Badge>
                  )}
                  {Number(student.fee_balance) > 0 && (
                    <Badge variant={Number(student.fee_balance) > 500000 ? 'danger' : 'warning'}>
                      {Number(student.fee_balance) > 500000 ? 'High Balance' : 'Partial Payment'}
                    </Badge>
                  )}
                </>
              ) : (
                <div className="text-xs text-slate-400 italic">
                  No active fee record found for this student in the current term.
                </div>
              )}
            </div>
          </RbacGate>

          {/* Attendance Record — Test 4.5 Requirement */}
          <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h5 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <ClipboardCheck className="w-3.5 h-3.5 text-emerald-400" />
                Attendance Record
              </h5>
              {attendanceSummary?.attendance_rate !== undefined && attendanceSummary?.attendance_rate !== null && (
                <Badge variant={attendanceSummary.below_threshold ? 'danger' : 'success'} size="sm">
                  {attendanceSummary.below_threshold ? 'At Risk (<75%)' : 'Good Standing'}
                </Badge>
              )}
            </div>

            {isLoadingAttendance ? (
              <div className="animate-pulse space-y-2">
                <div className="h-8 bg-slate-900 rounded-lg" />
              </div>
            ) : attendanceSummary && attendanceSummary.attendance_rate !== null ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-slate-900 rounded-xl border border-slate-700/60">
                  <span className="text-xs text-slate-300">Term Attendance Rate</span>
                  <span className={`text-sm font-bold font-mono ${attendanceSummary.below_threshold ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {attendanceSummary.attendance_rate}%
                  </span>
                </div>
                {attendanceRecords && attendanceRecords.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Recent Sessions</p>
                    <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
                      {attendanceRecords.slice(0, 5).map((rec: any) => (
                        <div key={rec.id} className="flex items-center justify-between p-2 bg-slate-900/80 rounded-lg border border-slate-800 text-xs">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-slate-400 text-[11px]">{rec.date}</span>
                            {rec.notes && (
                              <span className="text-slate-500 text-[10px] italic truncate max-w-[130px]">
                                ({rec.notes})
                              </span>
                            )}
                          </div>
                          <Badge
                            variant={
                              rec.status === 'present' ? 'success' :
                              rec.status === 'late' ? 'warning' :
                              rec.status === 'excused' ? 'info' : 'danger'
                            }
                            size="sm"
                          >
                            {rec.status.toUpperCase()}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic">
                No attendance sessions recorded for this student in the current active term.
              </div>
            )}
          </div>

          {/* Guardian Linkages */}
          <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 space-y-3">
            <h5 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Users className="w-3.5 h-3.5" />
              Guardians ({student.guardians?.length ?? 0})
            </h5>
            <div className="space-y-3">
              {(student.guardians ?? []).map((guardian) => (
                <div key={guardian.id} className="flex items-center justify-between p-3 bg-slate-900 rounded-xl border border-slate-700/60">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">
                        {guardian.first_name} {guardian.last_name}
                      </span>
                      {guardian.is_primary && (
                        <Badge variant="info" size="sm">Primary</Badge>
                      )}
                    </div>
                    <p className="text-[10px] text-slate-400 mt-0.5 capitalize">{guardian.relationship}</p>
                  </div>
                  <a
                    href={`tel:${guardian.phone}`}
                    className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    <Phone className="w-3.5 h-3.5" />
                    {guardian.phone}
                  </a>
                </div>
              ))}
              {(!student.guardians || student.guardians.length === 0) && (
                <p className="text-xs text-slate-400 text-center py-3">No guardians linked yet.</p>
              )}
            </div>
          </div>

          {/* Administrative Controls — Director Only */}
          {canDeleteStudent && (
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-5 space-y-3">
              <h5 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                Administrative Controls
              </h5>

              {student.is_active ? (
                <div className="space-y-3">
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Deactivating this student preserves all historical financial records, payments, and exam marks while removing them from active class registers.
                  </p>
                  <Button
                    variant="danger"
                    size="sm"
                    className="w-full"
                    leftIcon={<UserMinus className="w-4 h-4" />}
                    onClick={() => setDeactivateModalOpen(true)}
                  >
                    Deactivate Student
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="p-3.5 bg-slate-900/90 border border-amber-500/40 rounded-xl space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-amber-400" />
                      <p className="text-xs font-bold text-amber-400 uppercase tracking-wide">Student Record Inactive</p>
                    </div>
                    <p className="text-xs text-slate-300">
                      Reason: <span className="text-slate-400">{student.deactivation_reason || 'Transferred to another school'}</span>
                    </p>
                    <p className="text-xs text-slate-400">
                      Deactivated on: <span className="text-slate-300">{student.deactivated_at ? (student.deactivated_at.includes('T') ? student.deactivated_at.split('T')[0] : new Date(student.deactivated_at).toLocaleDateString()) : new Date().toISOString().split('T')[0]}</span>
                    </p>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    className="w-full"
                    leftIcon={<UserCheck className="w-4 h-4" />}
                    isLoading={isReactivating}
                    onClick={handleReactivate}
                  >
                    Reactivate Student Record
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Deactivation Confirmation Modal */}
      <Modal
        isOpen={deactivateModalOpen}
        onClose={() => setDeactivateModalOpen(false)}
        title="Confirm Student Deactivation"
        description="Safely deactivate student record without losing historical payments or marks"
        maxWidth="md"
      >
        <div className="space-y-4">
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-200">
            <strong>Note:</strong> This action soft-deactivates <strong className="text-white">{fullName}</strong> ({student?.admission_number || student?.student_id}). All historical attendance, marks, and financial ledgers will remain strictly preserved.
          </div>

          <Select
            label="Deactivation Reason"
            options={DEACTIVATION_REASONS}
            value={selectedReason}
            onChange={(e) => setSelectedReason(e.target.value)}
          />

          {selectedReason === 'Other' && (
            <TextInput
              label="Specify Reason"
              placeholder="e.g. Relocated out of district"
              value={customReason}
              onChange={(e) => setCustomReason(e.target.value)}
              required
            />
          )}

          {actionError && (
            <p className="text-xs text-rose-400">{actionError}</p>
          )}

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setDeactivateModalOpen(false)}
              disabled={isSubmittingDeactivate}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="danger"
              isLoading={isSubmittingDeactivate}
              leftIcon={<UserMinus className="w-4 h-4" />}
              onClick={handleDeactivate}
            >
              Confirm Deactivation
            </Button>
          </div>
        </div>
      </Modal>
      {/* Edit Student Modal */}
      <Modal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        title="Edit Student Details"
        description="Update student biographical info or class stream"
        maxWidth="md"
      >
        <form onSubmit={handleEditSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <TextInput
              label="First Name"
              value={editForm.first_name}
              onChange={(e) => setEditForm(prev => ({ ...prev, first_name: e.target.value }))}
              required
            />
            <TextInput
              label="Last Name"
              value={editForm.last_name}
              onChange={(e) => setEditForm(prev => ({ ...prev, last_name: e.target.value }))}
              required
            />
          </div>

          <TextInput
            label="Other Names"
            value={editForm.other_names}
            onChange={(e) => setEditForm(prev => ({ ...prev, other_names: e.target.value }))}
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Gender"
              options={[
                { value: 'M', label: 'Male' },
                { value: 'F', label: 'Female' },
              ]}
              value={editForm.gender}
              onChange={(e) => setEditForm(prev => ({ ...prev, gender: e.target.value }))}
            />
            <TextInput
              label="Date of Birth"
              type="date"
              value={editForm.date_of_birth}
              onChange={(e) => setEditForm(prev => ({ ...prev, date_of_birth: e.target.value }))}
            />
          </div>

          <Select
            label="Class Group"
            options={[
              { value: '', label: 'Select Class...' },
              ...(Array.isArray(classData) ? classData : []).map((c: any) => ({
                value: String(c.id),
                label: c.name,
              })),
            ]}
            value={editForm.current_class}
            onChange={(e) => setEditForm(prev => ({ ...prev, current_class: e.target.value }))}
          />

          {editError && (
            <p className="text-xs text-rose-400">{editError}</p>
          )}

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditModalOpen(false)}
              disabled={isSubmittingEdit}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={isSubmittingEdit}
            >
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>
    </Drawer>
  );
};

const InfoRow: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({
  icon, label, value,
}) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[10px] text-slate-500 uppercase tracking-wider flex items-center gap-1">
      <span className="text-slate-500">{icon}</span>
      {label}
    </span>
    <span className="text-xs font-semibold text-slate-200">{value}</span>
  </div>
);

