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
import { Modal } from '../../components/ui/Modal';
import { Select } from '../../components/ui/Select';
import { AutoSuggestInput } from '../../components/ui/AutoSuggestInput';
import { StudentDetailDrawer } from '../../components/students/StudentDetailDrawer';
import { AddStudentModal } from '../../components/students/AddStudentModal';
import { CsvImportModal } from '../../components/students/CsvImportModal';
import { UserPlus, Upload, Phone, Eye, UserMinus, UserCheck } from 'lucide-react';
import { RbacGate } from '../../components/auth/RbacGate';
import { useRbac } from '../../hooks/useRbac';

interface Student {
  id: string;
  student_id: string;
  admission_number?: string;
  full_name?: string;
  first_name: string;
  last_name: string;
  other_names?: string;
  gender: string;
  current_class?: number | string | { id: string | number; name: string };
  class_name?: string;
  current_class_name?: string;
  is_active: boolean;
  primary_guardian_phone?: string;
  fee_balance?: number;
  amount_paid?: number;
  fee_status?: string;
}

const feeStatusVariant = (balance: number, status?: string): BadgeVariant => {
  if (status === 'credit' || balance < 0) return 'success';
  if (status === 'cleared' || balance === 0) return 'success';
  if (status === 'partial') return 'warning';
  return 'neutral';
};

const feeStatusLabel = (balance: number, status?: string): string => {
  if (status === 'credit' || balance < 0) return 'Credit';
  if (status === 'cleared' || balance === 0) return 'Paid';
  if (status === 'partial') return 'Partial';
  return 'Unpaid';
};

const DEACTIVATION_REASONS = [
  { value: 'Transferred to another school', label: 'Transferred to another school' },
  { value: 'Graduated / Completed level', label: 'Graduated / Completed level' },
  { value: 'Withdrawn by parent/guardian', label: 'Withdrawn by parent/guardian' },
  { value: 'Disciplinary / Dismissed', label: 'Disciplinary / Dismissed' },
  { value: 'Financial constraints / Relocated', label: 'Financial constraints / Relocated' },
  { value: 'Other', label: 'Other (specify below)' },
];

export const StudentDirectoryPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { can } = useRbac();
  const canViewFinance = can('view:finance');
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [classFilter, setClassFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [deactivateStudent, setDeactivateStudent] = useState<Student | null>(null);
  const [selectedReason, setSelectedReason] = useState('Transferred to another school');
  const [customReason, setCustomReason] = useState('');
  const [isSubmittingDeactivate, setIsSubmittingDeactivate] = useState(false);
  const [reactivatingId, setReactivatingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');

  const handleDeactivate = async () => {
    if (!deactivateStudent) return;
    setIsSubmittingDeactivate(true);
    setActionError('');
    try {
      const reason = selectedReason === 'Other' ? (customReason.trim() || 'Deactivated by Director') : selectedReason;
      await apiClient.delete(`/students/${deactivateStudent.id}/`, {
        data: { reason }
      });
      queryClient.invalidateQueries({ queryKey: ['students'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail'] });
      queryClient.removeQueries({ queryKey: ['student-detail', deactivateStudent.id] });
      setDeactivateModalOpen(false);
      setDeactivateStudent(null);
      setCustomReason('');
    } catch (err: any) {
      setActionError(err.response?.data?.message || err.response?.data?.detail || 'Failed to deactivate student.');
    } finally {
      setIsSubmittingDeactivate(false);
    }
  };

  const handleDirectReactivate = async (student: Student) => {
    setReactivatingId(student.id);
    try {
      await apiClient.post(`/students/${student.id}/reactivate/`);
      queryClient.invalidateQueries({ queryKey: ['students'] });
      queryClient.invalidateQueries({ queryKey: ['student-detail'] });
      queryClient.removeQueries({ queryKey: ['student-detail', student.id] });
    } catch (err: any) {
      try {
        await apiClient.patch(`/students/${student.id}/`, { is_active: true });
        queryClient.invalidateQueries({ queryKey: ['students'] });
        queryClient.invalidateQueries({ queryKey: ['student-detail'] });
        queryClient.removeQueries({ queryKey: ['student-detail', student.id] });
      } catch (patchErr: any) {
        alert(patchErr.response?.data?.message || 'Failed to reactivate student.');
      }
    } finally {
      setReactivatingId(null);
    }
  };

  // Fetch students from backend API
  const { data, isLoading } = useQuery({
    queryKey: ['students', search, currentPage, pageSize, classFilter, statusFilter],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: currentPage,
        page_size: pageSize,
      };
      if (search) params.search = search;
      if (classFilter) params.current_class = classFilter;
      if (statusFilter === 'all') {
        params.include_inactive = 'true';
      } else if (statusFilter === 'active') {
        params.is_active = 'true';
      } else if (statusFilter === 'inactive') {
        params.is_active = 'false';
      }

      const res = await apiClient.get('/students/', { params });
      return res.data;
    },
    placeholderData: (prev) => prev,
  });

  // Fetch real class options from backend
  const { data: classData } = useQuery({
    queryKey: ['class-groups'],
    queryFn: async () => {
      const res = await apiClient.get('/students/classes/');
      return res.data?.results || res.data || [];
    },
  });

  const classOptions = (Array.isArray(classData) ? classData : []).map((c: any) => ({
    value: String(c.id),
    label: c.name,
  }));

  const studentsList: Student[] = data?.results || (Array.isArray(data) ? data : []);
  const totalCount: number = data?.count ?? studentsList.length;

  const columns: Column<Student>[] = [
    {
      header: 'Admission No.',
      cell: (row) => (
        <span className="font-mono text-xs text-emerald-400 font-semibold">
          {row.admission_number || row.student_id}
        </span>
      ),
    },
    {
      header: 'Full Name',
      cell: (row) => {
        const full = `${row.first_name} ${row.other_names ? row.other_names + ' ' : ''}${row.last_name}`;
        return (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] font-bold text-slate-300">
              {row.first_name[0]}{row.last_name[0]}
            </div>
            <span className="font-medium text-white">{full}</span>
          </div>
        );
      },
    },
    {
      header: 'Gender',
      cell: (row) => (
        <span className="text-xs text-slate-300">
          {row.gender === 'M' ? 'Male' : row.gender === 'F' ? 'Female' : row.gender}
        </span>
      ),
    },
    {
      header: 'Class / Stream',
      cell: (row) => {
        const cName = row.class_name || row.current_class_name || (typeof row.current_class === 'object' ? row.current_class?.name : null) || 'Unassigned';
        return <span className="text-xs text-slate-300 font-medium">{cName}</span>;
      },
    },
    {
      header: 'Guardian Phone',
      cell: (row) => {
        const phone = row.primary_guardian_phone;
        return phone ? (
          <span className="font-mono text-xs text-slate-300 flex items-center gap-1.5">
            <Phone className="w-3 h-3 text-emerald-400" />
            {phone}
          </span>
        ) : (
          <span className="text-xs text-slate-500 italic">No primary guardian</span>
        );
      },
    },
    {
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.is_active ? 'success' : 'neutral'} size="sm">
          {row.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    ...(canViewFinance ? [{
      header: 'Balance',
      cell: (row: Student) => {
        if (row.fee_balance === undefined || row.fee_balance === null) {
          return <span className="text-xs text-slate-500 italic">—</span>;
        }
        const bal = row.fee_balance;
        return (
          <div className="flex items-center gap-2">
            <span className={`font-mono text-xs font-semibold ${
              bal < 0 ? 'text-emerald-400' : bal === 0 ? 'text-emerald-400' : bal > 500000 ? 'text-rose-400' : 'text-amber-400'
            }`}>
              {bal < 0
                ? `-UGX ${Math.abs(bal).toLocaleString()}`
                : bal === 0
                ? 'UGX 0 (Cleared)'
                : `UGX ${bal.toLocaleString()}`}
            </span>
            <Badge variant={feeStatusVariant(bal, row.fee_status)} size="sm">
              {feeStatusLabel(bal, row.fee_status)}
            </Badge>
          </div>
        );
      },
    }] : []),
    {
      header: 'Actions',
      cell: (row: Student) => (
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={() => handleRowClick(row)}
            className="px-2.5 py-1 rounded-lg text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 hover:text-white transition-colors flex items-center gap-1"
            title="View student profile"
          >
            <Eye className="w-3.5 h-3.5" />
            <span>Profile</span>
          </button>
          {can('student:delete') && row.is_active && (
            <button
              type="button"
              onClick={() => {
                setDeactivateStudent(row);
                setActionError('');
                setDeactivateModalOpen(true);
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium text-rose-400 bg-rose-950/20 hover:bg-rose-950/60 border border-rose-800/30 transition-colors flex items-center gap-1"
              title="Deactivate student"
            >
              <UserMinus className="w-3.5 h-3.5" />
              <span>Deactivate</span>
            </button>
          )}
          {(can('student:edit') || can('student:delete')) && !row.is_active && (
            <button
              type="button"
              disabled={reactivatingId === row.id}
              onClick={() => handleDirectReactivate(row)}
              className="px-2.5 py-1 rounded-lg text-xs font-medium text-emerald-400 bg-emerald-950/20 hover:bg-emerald-950/60 border border-emerald-800/30 transition-colors flex items-center gap-1 disabled:opacity-50"
              title="Reactivate student"
            >
              <UserCheck className="w-3.5 h-3.5" />
              <span>{reactivatingId === row.id ? 'Reactivating...' : 'Reactivate'}</span>
            </button>
          )}
        </div>
      ),
    },
  ];

  const handleRowClick = (student: Student) => {
    setSelectedStudentId(student.id);
    setDrawerOpen(true);
  };

  const handleReset = () => {
    setSearch('');
    setClassFilter('');
    setStatusFilter('all');
    setCurrentPage(1);
  };

  const handleStudentAdded = () => {
    queryClient.invalidateQueries({ queryKey: ['students'] });
  };

  const activeFilters = [
    ...(classFilter
      ? [{ key: 'class', label: 'Class', value: classOptions.find((c: any) => c.value === classFilter)?.label || classFilter }]
      : []),
    ...(statusFilter !== 'all'
      ? [{ key: 'status', label: 'Status', value: statusFilter === 'active' ? 'Active' : 'Inactive' }]
      : []),
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Student Directory</h1>
          <p className="text-xs text-slate-400 mt-1">
            {isLoading ? 'Loading records...' : `${totalCount.toLocaleString()} enrolled students`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <RbacGate permission="student:csv_import" fallback={null}>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Upload className="w-4 h-4" />}
              onClick={() => setCsvModalOpen(true)}
            >
              Bulk Import CSV
            </Button>
          </RbacGate>
          <RbacGate permission="student:create" fallback={null}>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<UserPlus className="w-4 h-4" />}
              onClick={() => setAddModalOpen(true)}
            >
              Add Student
            </Button>
          </RbacGate>
        </div>
      </div>

      {/* Filter Bar */}
      <FilterBar
        searchValue={search}
        onSearchChange={(v) => { setSearch(v); setCurrentPage(1); }}
        searchPlaceholder="Search by name, admission no., or guardian phone..."
        activeFilters={activeFilters}
        onRemoveFilter={(key) => {
          if (key === 'class') setClassFilter('');
          if (key === 'status') setStatusFilter('all');
          setCurrentPage(1);
        }}
        onResetAll={handleReset}
      >
        <div className="w-40">
          <select
            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value as any); setCurrentPage(1); }}
          >
            <option value="all">All Statuses</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>

        <div className="w-48">
          <select
            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
            value={classFilter}
            onChange={(e) => { setClassFilter(e.target.value); setCurrentPage(1); }}
          >
            <option value="">All Classes</option>
            {classOptions.map((cls: any) => (
              <option key={cls.value} value={cls.value}>
                {cls.label}
              </option>
            ))}
          </select>
        </div>
      </FilterBar>

      {/* Student Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <DataTable
          columns={columns}
          data={studentsList}
          onRowClick={handleRowClick}
          isLoading={isLoading}
          emptyMessage="No students found matching the selected filters."
        />

        {totalCount > pageSize && (
          <div className="p-4 border-t border-slate-800">
            <TablePagination
              currentPage={currentPage}
              totalCount={totalCount}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              onPageSizeChange={(sz) => { setPageSize(sz); setCurrentPage(1); }}
            />
          </div>
        )}
      </div>

      {/* Modals & Drawers */}
      <StudentDetailDrawer
        studentId={selectedStudentId}
        isOpen={drawerOpen}
        onClose={() => { setDrawerOpen(false); setSelectedStudentId(null); }}
      />

      <AddStudentModal
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        classOptions={classOptions}
        onStudentAdded={handleStudentAdded}
      />

      <CsvImportModal
        isOpen={csvModalOpen}
        onClose={() => {
          setCsvModalOpen(false);
          queryClient.invalidateQueries({ queryKey: ['students'] });
        }}
      />

      {/* Deactivation Confirmation Modal */}
      <Modal
        isOpen={deactivateModalOpen}
        onClose={() => {
          setDeactivateModalOpen(false);
          setDeactivateStudent(null);
        }}
        title="Confirm Student Deactivation"
        description="Safely deactivate student record without losing historical payments or marks"
        maxWidth="md"
      >
        <div className="space-y-4">
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-200">
            <strong>Note:</strong> This action soft-deactivates{' '}
            <strong className="text-white">
              {deactivateStudent?.first_name} {deactivateStudent?.last_name}
            </strong>{' '}
            ({deactivateStudent?.admission_number || deactivateStudent?.student_id}). All historical attendance, marks, and financial ledgers will remain strictly preserved.
          </div>

          <Select
            label="Deactivation Reason"
            options={DEACTIVATION_REASONS}
            value={selectedReason}
            onChange={(e) => setSelectedReason(e.target.value)}
          />

          {selectedReason === 'Other' && (
            <AutoSuggestInput
              label="Specify Reason"
              placeholder="e.g. Relocated out of district"
              value={customReason}
              onChange={setCustomReason}
              category="deactivation_reasons"
              showChips={true}
            />
          )}

          {actionError && (
            <p className="text-xs text-rose-400">{actionError}</p>
          )}

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setDeactivateModalOpen(false);
                setDeactivateStudent(null);
              }}
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
    </div>
  );
};
