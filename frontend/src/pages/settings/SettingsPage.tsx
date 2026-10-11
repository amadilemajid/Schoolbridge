import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { TextInput } from '../../components/ui/TextInput';
import { AlertBanner } from '../../components/ui/AlertBanner';
import { Badge } from '../../components/ui/Badge';
import { InviteStaffModal } from '../../components/settings/InviteStaffModal';
import {
  School,
  Bell,
  Shield,
  Plus,
  Save,
  Users,
  ChevronRight,
} from 'lucide-react';

type SettingsSection = 'school' | 'notifications' | 'users' | 'audit';

interface SchoolSettings {
  name: string;
  registration_number: string;
  district: string;
  head_teacher: string;
  phone: string;
  email: string;
  term_start_date: string;
  term_end_date: string;
  messaging_window_start: string;
  messaging_window_end: string;
  whatsapp_pause_reason: string;
  whatsapp_paused_until?: string;
}

interface AuditLog {
  id: string;
  user: string;
  action: string;
  model: string;
  object_id: string;
  timestamp: string;
  ip_address: string;
}

export const SettingsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeSection, setActiveSection] = useState<SettingsSection>('school');
  const [saved, setSaved] = useState(false);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);

  // Fetch school settings
  const { data: settings, isLoading: loadingSettings } = useQuery({
    queryKey: ['school-settings'],
    queryFn: async () => {
      const res = await apiClient.get('/schools/settings/');
      return res.data as SchoolSettings;
    },
  });

  const [form, setForm] = useState<Partial<SchoolSettings>>({});

  const set = (field: keyof SchoolSettings) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setSaved(false);
    };

  const effectiveSettings = { ...settings, ...form };

  // Save settings mutation
  const { mutate: saveSettings, isPending: saving } = useMutation({
    mutationFn: async () => {
      const res = await apiClient.patch('/schools/settings/', form);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['school-settings'] });
      setSaved(true);
    },
  });

  // Fetch audit logs
  const { data: auditData, isLoading: loadingAudit } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: async () => {
      const res = await apiClient.get('/audit/logs/?page_size=20');
      return (res.data?.results || res.data || []) as AuditLog[];
    },
    enabled: activeSection === 'audit',
  });

  // Fetch real staff list from API
  const { data: staffData, isLoading: loadingStaff } = useQuery({
    queryKey: ['staff-list'],
    queryFn: async () => {
      const res = await apiClient.get('/auth/users/');
      return (res.data?.results || res.data || []) as Array<{
        id: string;
        first_name: string;
        last_name: string;
        email: string;
        role: string;
        is_active: boolean;
      }>;
    },
    enabled: activeSection === 'users',
  });

  const staffList = (staffData || []).map((u) => ({
    id: u.id,
    name: `${u.first_name} ${u.last_name}`.trim() || u.email,
    email: u.email,
    role: u.role,
    is_active: u.is_active,
  }));

  const sections = [
    { id: 'school', label: 'School Profile', icon: <School className="w-4 h-4" /> },
    { id: 'notifications', label: 'Notifications & Messaging', icon: <Bell className="w-4 h-4" /> },
    { id: 'users', label: 'Staff & Roles', icon: <Users className="w-4 h-4" /> },
    { id: 'audit', label: 'Audit Logs', icon: <Shield className="w-4 h-4" /> },
  ] as const;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Settings & Administration</h1>
        <p className="text-xs text-slate-400 mt-1">
          School profile, messaging windows, staff roles, and system audit logs
        </p>
      </div>

      {saved && (
        <AlertBanner
          type="success"
          title="Settings Saved"
          message="School configuration updated successfully."
          onDismiss={() => setSaved(false)}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Sidebar Navigation */}
        <aside className="lg:col-span-3">
          <nav className="bg-slate-800/80 border border-slate-700/60 rounded-2xl overflow-hidden">
            {sections.map((sec) => (
              <button
                key={sec.id}
                onClick={() => setActiveSection(sec.id)}
                className={`w-full text-left flex items-center justify-between gap-3 px-4 py-3.5 text-xs font-semibold transition-all border-b border-slate-700/60 last:border-b-0 ${
                  activeSection === sec.id
                    ? 'bg-emerald-500/10 text-emerald-400 border-l-2 border-l-emerald-500'
                    : 'text-slate-400 hover:text-white hover:bg-slate-700/30'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  {sec.icon}
                  {sec.label}
                </div>
                <ChevronRight className="w-3.5 h-3.5 opacity-50" />
              </button>
            ))}
          </nav>
        </aside>

        {/* Content Panel */}
        <div className="lg:col-span-9 space-y-5">

          {/* School Profile */}
          {activeSection === 'school' && (
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-6 space-y-5">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <School className="w-4 h-4 text-emerald-400" /> School Profile
              </h3>
              {loadingSettings ? (
                <div className="animate-pulse space-y-3">
                  {[...Array(6)].map((_, i) => <div key={i} className="h-12 bg-slate-700 rounded-xl" />)}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <TextInput
                    label="School Name"
                    value={effectiveSettings.name || ''}
                    onChange={set('name')}
                    required
                  />
                  <TextInput
                    label="MoES Registration Number"
                    value={effectiveSettings.registration_number || ''}
                    onChange={set('registration_number')}
                  />
                  <TextInput
                    label="District"
                    value={effectiveSettings.district || ''}
                    onChange={set('district')}
                  />
                  <TextInput
                    label="Head Teacher"
                    value={effectiveSettings.head_teacher || ''}
                    onChange={set('head_teacher')}
                  />
                  <TextInput
                    label="School Phone"
                    value={effectiveSettings.phone || ''}
                    onChange={set('phone')}
                  />
                  <TextInput
                    label="School Email"
                    type="email"
                    value={effectiveSettings.email || ''}
                    onChange={set('email')}
                  />
                  <TextInput
                    label="Term Start Date"
                    type="date"
                    value={effectiveSettings.term_start_date || ''}
                    onChange={set('term_start_date')}
                  />
                  <TextInput
                    label="Term End Date"
                    type="date"
                    value={effectiveSettings.term_end_date || ''}
                    onChange={set('term_end_date')}
                  />
                </div>
              )}
              <div className="flex justify-end pt-2 border-t border-slate-700">
                <Button
                  variant="primary"
                  size="sm"
                  isLoading={saving}
                  leftIcon={<Save className="w-4 h-4" />}
                  onClick={() => saveSettings()}
                >
                  Save Profile
                </Button>
              </div>
            </div>
          )}

          {/* Notifications & Messaging Window */}
          {activeSection === 'notifications' && (
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-6 space-y-5">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Bell className="w-4 h-4 text-emerald-400" /> Messaging Configuration
              </h3>

              <AlertBanner
                type="info"
                title="Uganda Communication Hours"
                message="Default messaging window is 8:00 AM – 9:00 PM EAT to comply with Uganda's Data Protection Act guidelines on communication hours."
              />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <TextInput
                  label="Messaging Window Start (EAT)"
                  type="time"
                  value={effectiveSettings.messaging_window_start || '08:00'}
                  onChange={set('messaging_window_start')}
                />
                <TextInput
                  label="Messaging Window End (EAT)"
                  type="time"
                  value={effectiveSettings.messaging_window_end || '21:00'}
                  onChange={set('messaging_window_end')}
                />
              </div>

              <div className="space-y-2">
                <TextInput
                  label="Pause Reason (Director Override)"
                  placeholder="e.g. Waiting for UNEB results announcement"
                  value={effectiveSettings.whatsapp_pause_reason || ''}
                  onChange={set('whatsapp_pause_reason')}
                />
                <TextInput
                  label="Paused Until (leave blank to clear)"
                  type="datetime-local"
                  value={effectiveSettings.whatsapp_paused_until || ''}
                  onChange={set('whatsapp_paused_until' as any)}
                />
              </div>

              <div className="flex justify-end pt-2 border-t border-slate-700">
                <Button
                  variant="primary"
                  size="sm"
                  isLoading={saving}
                  leftIcon={<Save className="w-4 h-4" />}
                  onClick={() => saveSettings()}
                >
                  Save Messaging Settings
                </Button>
              </div>
            </div>
          )}

          {/* Staff & Roles */}
          {activeSection === 'users' && (
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-6 space-y-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Users className="w-4 h-4 text-emerald-400" /> Staff & Role Management
                </h3>
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Plus className="w-3.5 h-3.5" />}
                  onClick={() => setInviteModalOpen(true)}
                >
                  Invite Staff
                </Button>
              </div>

              <div className="space-y-2">
                {loadingStaff ? (
                <div className="animate-pulse space-y-2">
                  {[...Array(4)].map((_, i) => <div key={i} className="h-14 bg-slate-700 rounded-xl" />)}
                </div>
              ) : staffList.length === 0 ? (
                <div className="py-8 text-center text-slate-500 text-xs">No staff members found.</div>
              ) : (
                staffList.map((staff) => (
                  <div
                    key={staff.id}
                    className="flex items-center justify-between p-3.5 bg-slate-900 border border-slate-700/60 rounded-xl"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-500 flex items-center justify-center text-white text-sm font-bold">
                        {staff.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-white">{staff.name}</p>
                        <p className="text-[10px] text-slate-400">{staff.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={staff.role === 'director' ? 'danger' : staff.role === 'bursar' ? 'success' : 'info'}>
                        {staff.role}
                      </Badge>
                      <Badge variant={staff.is_active ? 'success' : 'neutral'}>
                        {staff.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </div>
                  </div>
                ))
              )}
              </div>
            </div>
          )}

          {/* Audit Logs */}
          {activeSection === 'audit' && (
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl p-6 space-y-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Shield className="w-4 h-4 text-emerald-400" /> System Audit Trail
              </h3>

              {loadingAudit ? (
                <div className="animate-pulse space-y-2">
                  {[...Array(8)].map((_, i) => <div key={i} className="h-12 bg-slate-700 rounded-xl" />)}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-slate-400 uppercase tracking-wider border-b border-slate-700">
                        <th className="py-2 px-3 text-left">User</th>
                        <th className="py-2 px-3 text-left">Action</th>
                        <th className="py-2 px-3 text-left">Object</th>
                        <th className="py-2 px-3 text-left">IP Address</th>
                        <th className="py-2 px-3 text-left">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/50">
                      {(auditData || []).map((log) => (
                        <tr key={log.id} className="hover:bg-slate-700/20 transition-colors">
                          <td className="py-3 px-3 font-semibold text-white">{log.user}</td>
                          <td className="py-3 px-3">
                            <Badge
                              variant={log.action === 'DELETE' ? 'danger' : log.action === 'CREATE' ? 'success' : 'info'}
                              size="sm"
                            >
                              {log.action}
                            </Badge>
                          </td>
                          <td className="py-3 px-3 text-slate-300 font-mono">{log.model} #{log.object_id}</td>
                          <td className="py-3 px-3 text-slate-400 font-mono">{log.ip_address}</td>
                          <td className="py-3 px-3 text-slate-400">
                            {new Date(log.timestamp).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <InviteStaffModal
        isOpen={inviteModalOpen}
        onClose={() => setInviteModalOpen(false)}
      />
    </div>
  );
};

