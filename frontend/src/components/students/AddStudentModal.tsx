import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { UgandaPhoneInput } from '../ui/UgandaPhoneInput';
import { Select } from '../ui/Select';
import { UserPlus, CheckCircle2 } from 'lucide-react';
import { validateUgandaPhone, formatUgandaPhoneInternational } from '../../utils/telecom';

interface AddStudentModalProps {
  isOpen: boolean;
  onClose: () => void;
  classOptions: { value: string; label: string }[];
  onStudentAdded?: (student: any) => void;
}

const GENDER_OPTIONS = [
  { value: '', label: 'Select Gender...' },
  { value: 'M', label: 'Male' },
  { value: 'F', label: 'Female' },
];

const RELATIONSHIP_OPTIONS = [
  { value: 'father', label: 'Father' },
  { value: 'mother', label: 'Mother' },
  { value: 'guardian', label: 'Guardian' },
  { value: 'uncle', label: 'Uncle' },
  { value: 'aunt', label: 'Aunt' },
  { value: 'sibling', label: 'Sibling' },
];

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'lg', label: 'Luganda' },
  { value: 'rn', label: 'Runyankole' },
  { value: 'ach', label: 'Acholi' },
];

export const AddStudentModal: React.FC<AddStudentModalProps> = ({
  isOpen,
  onClose,
  classOptions,
  onStudentAdded,
}) => {
  const queryClient = useQueryClient();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [successStudent, setSuccessStudent] = useState<any | null>(null);

  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    other_names: '',
    admission_number: '',
    date_of_birth: '',
    gender: '',
    current_class: '',
    guardian_first_name: '',
    guardian_last_name: '',
    guardian_phone: '',
    guardian_relationship: 'Father',
    guardian_language: 'en',
  });

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!formData.first_name.trim()) errs.first_name = 'First name is required.';
    if (!formData.last_name.trim()) errs.last_name = 'Last name is required.';
    if (!formData.date_of_birth) errs.date_of_birth = 'Date of birth is required.';
    if (!formData.gender) errs.gender = 'Gender is required.';
    if (!formData.current_class) errs.current_class = 'Class stream is required.';
    if (!formData.guardian_first_name.trim()) errs.guardian_first_name = 'Guardian name is required.';
    
    const phoneVal = validateUgandaPhone(formData.guardian_phone);
    if (!phoneVal.isValid) {
      errs.guardian_phone = phoneVal.error || 'Enter a valid 10-digit Uganda phone number (e.g. 0771234567).';
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const { mutate, isPending } = useMutation({
    mutationFn: async () => {
      const payload = {
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        other_names: formData.other_names ? formData.other_names.trim() : undefined,
        admission_number: formData.admission_number.trim() || undefined,
        date_of_birth: formData.date_of_birth,
        gender: formData.gender,
        current_class: formData.current_class || undefined,
        admission_date: new Date().toISOString().split('T')[0],
        guardian_first_name: formData.guardian_first_name.trim(),
        guardian_last_name: formData.guardian_last_name.trim() || formData.guardian_first_name.trim(),
        guardian_phone: formatUgandaPhoneInternational(formData.guardian_phone),
        guardian_relationship: formData.guardian_relationship,
      };

      const res = await apiClient.post('/students/', payload);
      return res.data;
    },
    onSuccess: (data) => {
      setSuccessStudent(data);
      if (onStudentAdded) {
        onStudentAdded(data);
      }
      queryClient.invalidateQueries({ queryKey: ['students'] });
    },
    onError: (err: any) => {
      const detail = err.response?.data;
      if (detail && typeof detail === 'object') {
        const errs: Record<string, string> = {};
        Object.entries(detail).forEach(([k, v]) => {
          errs[k] = Array.isArray(v) ? (v as string[])[0] : String(v);
        });
        setErrors(errs);
      } else {
        setErrors({ general: 'Failed to create student record. Please try again.' });
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) mutate();
  };

  const handleClose = () => {
    setSuccessStudent(null);
    setFormData({
      first_name: '', last_name: '', other_names: '', admission_number: '', date_of_birth: '',
      gender: '', current_class: '', guardian_first_name: '', guardian_last_name: '',
      guardian_phone: '', guardian_relationship: 'Father', guardian_language: 'en',
    });
    setErrors({});
    onClose();
  };

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
    setErrors((prev) => { const next = { ...prev }; delete next[field]; return next; });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Enrol New Student"
      description="Create student record with admission number and primary guardian contact"
      maxWidth="xl"
    >
      {successStudent ? (
        <div className="text-center py-6 space-y-4">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto" />
          <h4 className="text-base font-bold text-white">Student Enrolled Successfully!</h4>
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-xs space-y-2 inline-block text-left min-w-[320px]">
            <p className="text-slate-300 flex justify-between gap-4">
              <span className="text-slate-400">Admission No.:</span> 
              <span className="font-mono text-emerald-400 font-bold">{successStudent.admission_number || successStudent.student_id || 'Assigned'}</span>
            </p>
            <p className="text-slate-300 flex justify-between gap-4">
              <span className="text-slate-400">Name:</span> 
              <span className="font-bold text-white">
                {successStudent.full_name || `${successStudent.first_name || formData.first_name} ${successStudent.other_names ? successStudent.other_names + ' ' : ''}${successStudent.last_name || formData.last_name}`}
              </span>
            </p>
            <p className="text-slate-300 flex justify-between gap-4">
              <span className="text-slate-400">Class:</span> 
              <span className="text-white font-medium">
                {successStudent.class_name || successStudent.current_class_name || (classOptions.find(c => String(c.value) === String(formData.current_class))?.label) || 'Assigned'}
              </span>
            </p>
            <p className="text-slate-300 flex justify-between gap-4">
              <span className="text-slate-400">Guardian Phone:</span> 
              <span className="font-mono text-emerald-300">
                {successStudent.primary_guardian_phone || successStudent.guardians?.[0]?.phone || formData.guardian_phone}
              </span>
            </p>
          </div>
          <div>
            <Button variant="primary" onClick={handleClose}>
              Done & View Directory
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Student Information</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextInput label="First Name" value={formData.first_name} onChange={set('first_name')} error={errors.first_name} required />
            <TextInput label="Last Name" value={formData.last_name} onChange={set('last_name')} error={errors.last_name} required />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextInput label="Other Names" placeholder="Optional middle or other names" value={formData.other_names} onChange={set('other_names')} />
            <TextInput
              label="Admission No."
              placeholder="e.g. KDA-2026-006 (leave blank to auto-generate)"
              value={formData.admission_number}
              onChange={set('admission_number')}
              error={errors.admission_number}
              helperText="Auto-assigned if left blank"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <TextInput label="Date of Birth" type="date" value={formData.date_of_birth} onChange={set('date_of_birth')} error={errors.date_of_birth} required />
            <Select label="Gender" options={GENDER_OPTIONS} value={formData.gender} onChange={set('gender')} error={errors.gender} required />
            <Select label="Class" options={[{ value: '', label: 'Select Class...' }, ...classOptions]} value={formData.current_class} onChange={set('current_class')} error={errors.current_class} required />
          </div>

          <div className="border-t border-slate-800 pt-4">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Primary Guardian</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextInput label="Guardian First Name" value={formData.guardian_first_name} onChange={set('guardian_first_name')} error={errors.guardian_first_name} required />
              <TextInput label="Guardian Last Name" value={formData.guardian_last_name} onChange={set('guardian_last_name')} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
              <UgandaPhoneInput label="Guardian Phone" value={formData.guardian_phone} onChange={set('guardian_phone')} error={errors.guardian_phone} required />
              <div className="grid grid-cols-2 gap-3">
                <Select label="Relationship" options={RELATIONSHIP_OPTIONS} value={formData.guardian_relationship} onChange={set('guardian_relationship')} />
                <Select label="Preferred Language" options={LANGUAGE_OPTIONS} value={formData.guardian_language} onChange={set('guardian_language')} />
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button type="button" variant="secondary" onClick={handleClose}>Cancel</Button>
            <Button type="submit" variant="primary" isLoading={isPending} leftIcon={<UserPlus className="w-4 h-4" />}>
              Enrol Student
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
};

