import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { TextInput } from '../../components/ui/TextInput';
import { School, Lock, ArrowRight, Mail } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [usernameOrPhone, setUsernameOrPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!usernameOrPhone.trim()) {
      setError('Please enter your email or phone number.');
      return;
    }

    if (!password) {
      setError('Please enter your password.');
      return;
    }

    setIsLoading(true);
    try {
      await login(usernameOrPhone.trim(), password);
      navigate('/');
    } catch (err: any) {
      const data = err.response?.data;
      let msg = 'Invalid login credentials. Please check your details and try again.';
      if (data) {
        if (typeof data.detail === 'string') {
          msg = data.detail;
        } else if (Array.isArray(data.non_field_errors) && data.non_field_errors.length > 0) {
          msg = data.non_field_errors[0];
        } else if (typeof data.non_field_errors === 'string') {
          msg = data.non_field_errors;
        } else if (typeof data === 'string') {
          msg = data;
        } else if (data.detail && typeof data.detail === 'object') {
          msg = Object.values(data.detail).flat().join(' ');
        }
      }
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      {/* Background Ambient Glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-xl border border-slate-700/80 rounded-2xl shadow-2xl p-6 sm:p-8 relative z-10">
        {/* Header Branding */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center shadow-xl shadow-emerald-900/40 mb-4">
            <School className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            School<span className="text-emerald-400">Bridge</span>
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Multi-Tenant School Automation Platform
          </p>
        </div>

        {/* Global Form Error Banner */}
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium">
            {error}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <TextInput
            id="login-identifier"
            label="Email or Phone Number"
            placeholder="e.g. teacher@stmarys.ug or 0771234567"
            helperText="Enter your registered school email address or phone number"
            value={usernameOrPhone}
            onChange={(e) => setUsernameOrPhone(e.target.value)}
            leftIcon={<Mail className="w-4 h-4 text-slate-400" />}
            required
            autoFocus
          />

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="login-password" className="text-sm font-medium text-slate-300">
                Password
              </label>
              <Link
                to="/auth/reset-password"
                className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 transition-colors focus:outline-none focus:underline"
              >
                Forgot password?
              </Link>
            </div>
            <TextInput
              id="login-password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              leftIcon={<Lock className="w-4 h-4 text-slate-400" />}
              required
            />
          </div>

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full mt-2"
            isLoading={isLoading}
            rightIcon={<ArrowRight className="w-4 h-4" />}
          >
            Sign In to Portal
          </Button>
        </form>

        {/* Quick Demo Credentials — DEV ONLY, hidden in production */}
        {import.meta.env.DEV && (
          <div className="mt-6 pt-5 border-t border-slate-700/60">
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2.5 text-center">
              Dev Quick Login
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <button
                type="button"
                onClick={() => {
                  setUsernameOrPhone('director@stmarys.ug');
                  setPassword('Demo@12345');
                  setError(null);
                }}
                className="px-2 py-1.5 bg-slate-900 border border-slate-700 hover:border-emerald-500 rounded-lg text-[11px] font-semibold text-emerald-300 transition-colors text-center"
              >
                Director
              </button>
              <button
                type="button"
                onClick={() => {
                  setUsernameOrPhone('bursar@stmarys.ug');
                  setPassword('Demo@12345');
                  setError(null);
                }}
                className="px-2 py-1.5 bg-slate-900 border border-slate-700 hover:border-emerald-500 rounded-lg text-[11px] font-semibold text-teal-400 transition-colors text-center"
              >
                Bursar
              </button>
              <button
                type="button"
                onClick={() => {
                  setUsernameOrPhone('teacher@stmarys.ug');
                  setPassword('Demo@12345');
                  setError(null);
                }}
                className="px-2 py-1.5 bg-slate-900 border border-slate-700 hover:border-emerald-500 rounded-lg text-[11px] font-semibold text-indigo-400 transition-colors text-center"
              >
                Teacher (Ruth)
              </button>
              <button
                type="button"
                onClick={() => {
                  setUsernameOrPhone('teacher_b@stmarys.ug');
                  setPassword('Demo@12345');
                  setError(null);
                }}
                className="px-2 py-1.5 bg-slate-900 border border-slate-700 hover:border-emerald-500 rounded-lg text-[11px] font-semibold text-purple-400 transition-colors text-center"
              >
                Teacher (Moses)
              </button>
            </div>
          </div>
        )}

        {/* Footer info */}
        <div className="mt-6 text-center text-xs text-slate-500 border-t border-slate-700/60 pt-4">
          <span>Uganda Data Protection & Privacy Act 2019 Compliant</span>
        </div>
      </div>
    </div>
  );
};
