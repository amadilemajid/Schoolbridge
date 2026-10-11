import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldX, ArrowLeft, LogOut, User } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';

interface UnauthorizedPageProps {
  requiredPermission?: string;
  backTo?: string;
  inline?: boolean;
}

const PERMISSION_LABELS: Record<string, string> = {
  'view:finance': 'Finance Dashboard',
  'finance:reconcile': 'MoMo Reconciliation',
  'view:reports': 'Reports',
  'view:settings': 'Settings',
  'view:communications': 'Messaging Hub',
  'payment:record': 'Record Payment',
  'payment:plan': 'Payment Plans',
  'payment:link': 'Payment Links',
  'settings:users': 'User Management',
  'settings:audit': 'Audit Log',
};

const ROLE_DISPLAY: Record<string, { label: string; color: string }> = {
  teacher:      { label: 'Teacher',      color: 'text-blue-400' },
  school_admin: { label: 'School Admin', color: 'text-violet-400' },
  bursar:       { label: 'Bursar',       color: 'text-amber-400' },
  director:     { label: 'Director',     color: 'text-emerald-400' },
  super_admin:  { label: 'Super Admin',  color: 'text-rose-400' },
};

export const UnauthorizedPage: React.FC<UnauthorizedPageProps> = ({
  requiredPermission,
  backTo = '/',
  inline = false,
}) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const roleInfo = user ? (ROLE_DISPLAY[user.role] ?? { label: user.role, color: 'text-slate-400' }) : null;
  const featureName = requiredPermission
    ? (PERMISSION_LABELS[requiredPermission] ?? requiredPermission)
    : 'this resource';

  if (inline) {
    return (
      <div className="flex items-start gap-3 p-4 bg-rose-950/30 border border-rose-500/30 rounded-xl">
        <ShieldX className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-rose-300">Access Denied — Unauthorized</p>
          <p className="text-xs text-rose-400/80 mt-0.5">
            Your role (<span className="font-semibold">{roleInfo?.label ?? 'Unknown'}</span>) does not
            have permission to access {featureName}. Contact your Director or School Administrator.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-6">
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-rose-500/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 w-full max-w-md text-center">
        {/* Shield Icon */}
        <div className="mx-auto w-20 h-20 rounded-3xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-6 shadow-xl shadow-rose-900/20">
          <ShieldX className="w-10 h-10 text-rose-400" />
        </div>

        {/* Status */}
        <p className="text-7xl font-black text-rose-500/15 tracking-tighter font-mono leading-none">403</p>
        <h1 className="text-2xl font-bold text-white tracking-tight mt-2">Access Denied</h1>
        <p className="text-slate-400 text-sm mt-2 leading-relaxed">
          You are not authorised to access{' '}
          <span className="text-rose-300 font-semibold">{featureName}</span>.
        </p>

        {/* Identity Card */}
        {user && (
          <div className="mt-6 p-4 bg-slate-800/70 border border-slate-700/60 rounded-xl text-left space-y-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-slate-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white truncate">
                  {user.first_name} {user.last_name}
                </p>
                <p className="text-[11px] text-slate-400 truncate">{user.email}</p>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border border-slate-600 bg-slate-700/50 shrink-0 ${roleInfo?.color ?? 'text-slate-400'}`}>
                {roleInfo?.label}
              </span>
            </div>

            <div className="pt-2 border-t border-slate-700/50">
              <p className="text-[11px] text-slate-500 leading-relaxed">
                The <span className={`font-semibold ${roleInfo?.color}`}>{roleInfo?.label}</span> role
                does not have access to financial records. Only{' '}
                <span className="text-emerald-400 font-semibold">Bursar</span>,{' '}
                <span className="text-emerald-400 font-semibold">Director</span>, or{' '}
                <span className="text-emerald-400 font-semibold">School Admin</span> can access{' '}
                {featureName}.
              </p>
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="mt-6 flex flex-col gap-3">
          <Button
            variant="primary"
            leftIcon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate(backTo, { replace: true })}
            className="w-full"
          >
            Go Back to Dashboard
          </Button>
          <Button
            variant="ghost"
            leftIcon={<LogOut className="w-4 h-4" />}
            onClick={logout}
            className="w-full text-slate-400 hover:text-rose-300"
          >
            Log Out and Switch Account
          </Button>
        </div>

        {/* Audit timestamp */}
        <p className="mt-6 text-[10px] text-slate-600">
          This access attempt has been recorded. Timestamp: {new Date().toISOString()}
        </p>
      </div>
    </div>
  );
};
