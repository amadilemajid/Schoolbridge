import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { UgandaPhoneInput } from '../ui/UgandaPhoneInput';
import { Select } from '../ui/Select';
import { UserPlus, CheckCircle2, Copy, Check } from 'lucide-react';

import { validateUgandaPhone, formatUgandaPhoneInternational } from '../../utils/telecom';

interface InviteStaffModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ROLE_OPTIONS = [
  { value: 'teacher', label: 'Class Teacher' },
  { value: 'bursar', label: 'School Bursar' },
  { value: 'school_admin', label: 'School Administrator' },
  { value: 'director', label: 'Director / Head Teacher' },
];

export const InviteStaffModal: React.FC<InviteStaffModalProps> = ({
  isOpen,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [role, setRole] = useState('teacher');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [inviteResult, setInviteResult] = useState<{
    temp_password?: string;
    activation_url?: string;
    email_sent?: boolean;
  } | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const { mutate: inviteStaff, isPending } = useMutation({
    mutationFn: async () => {
      const payload = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim() || undefined,
        phone_number: phone ? formatUgandaPhoneInternational(phone) : undefined,
        role,
      };
      // Try /schools/staff/invite/ or fallback to /auth/staff/invite/
      try {
        const res = await apiClient.post('/schools/staff/invite/', payload);
        return res.data;
      } catch (err: any) {
        if (err.response?.status === 404) {
          const res = await apiClient.post('/auth/staff/invite/', payload);
          return res.data;
        }
        throw err;
      }
    },
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['staff-list'] });
      setInviteResult(data);
      setSuccess(true);
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Failed to send staff invitation. Check email/phone uniqueness.';
      setError(msg);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!firstName.trim() || !lastName.trim()) {
      setError('First and last name are required.');
      return;
    }
    if (phone) {
      const phoneVal = validateUgandaPhone(phone);
      if (!phoneVal.isValid) {
        setError(phoneVal.error || 'Please enter a valid 10-digit Ugandan phone number (e.g. 0771234567).');
        return;
      }
    }
    inviteStaff();
  };

  const handleClose = () => {
    setFirstName('');
    setLastName('');
    setEmail('');
    setPhone('');
    setRole('teacher');
    setError(null);
    setSuccess(false);
    setInviteResult(null);
    setCopiedKey(null);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Invite New Staff Member"
      description="Send an invitation link and assign role permissions"
      maxWidth="lg"
    >
      {success ? (
        <div className="py-4 space-y-4">
          <div className="text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto" />
            <h4 className="text-base font-bold text-white mt-2">Account Created!</h4>
            <p className="text-xs text-slate-300 mt-1">
              Staff member <strong>{firstName} {lastName}</strong> has been registered successfully.
              {inviteResult?.email_sent ? ' An invitation email has been sent.' : ' You can provide credentials directly below.'}
            </p>
          </div>

          {inviteResult?.temp_password && (
            <div className="bg-slate-900 border border-slate-750 rounded-xl p-3.5 space-y-3 text-xs">
              <div>
                <label className="text-[11px] font-semibold text-slate-400 block mb-1">
                  Temporary Password
                </label>
                <div className="flex items-center justify-between bg-slate-950 px-3 py-2 rounded-lg border border-slate-800">
                  <span className="font-mono text-emerald-400 font-bold select-all">
                    {inviteResult.temp_password}
                  </span>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(inviteResult.temp_password!, 'pass')}
                    className="text-slate-400 hover:text-white flex items-center gap-1 text-[11px] cursor-pointer"
                  >
                    {copiedKey === 'pass' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedKey === 'pass' ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>

              {inviteResult.activation_url && (
                <div>
                  <label className="text-[11px] font-semibold text-slate-400 block mb-1">
                    Direct Activation Link (Valid 48h)
                  </label>
                  <div className="flex items-center justify-between bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 gap-2">
                    <span className="font-mono text-slate-300 truncate text-[11px] select-all flex-1">
                      {inviteResult.activation_url}
                    </span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(inviteResult.activation_url!, 'link')}
                      className="text-slate-400 hover:text-white flex items-center gap-1 text-[11px] shrink-0 cursor-pointer"
                    >
                      {copiedKey === 'link' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      {copiedKey === 'link' ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="text-center pt-2">
            <Button variant="primary" onClick={handleClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextInput
              label="First Name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              required
            />
            <TextInput
              label="Last Name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextInput
              label="Email Address"
              type="email"
              placeholder="e.g. teacher@school.ug"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <UgandaPhoneInput
              label="Phone Number"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </div>

          <Select
            label="Assigned System Role"
            options={ROLE_OPTIONS}
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button type="button" variant="secondary" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={isPending}
              leftIcon={<UserPlus className="w-4 h-4" />}
            >
              Send Invitation
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
};
