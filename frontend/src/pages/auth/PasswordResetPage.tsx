import React, { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { TextInput } from '../../components/ui/TextInput';
import { apiClient } from '../../api/client';
import {
  School,
  ArrowLeft,
  CheckCircle2,
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  KeyRound,
  ExternalLink,
} from 'lucide-react';

export const PasswordResetPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // If token is present in the URL query string, we are in confirmation (Phase 2) mode
  const tokenFromUrl = searchParams.get('token') || '';

  // Phase 1 (Request) State
  const [identifier, setIdentifier] = useState('');
  const [requestSubmitted, setRequestSubmitted] = useState(false);
  const [requestSuccessMessage, setRequestSuccessMessage] = useState('');
  const [devResetUrl, setDevResetUrl] = useState<string | null>(null);

  // Phase 2 (Confirm / Set Password) State
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [confirmSuccess, setConfirmSuccess] = useState(false);

  // Shared UI state
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Clear errors on mode or query change
  useEffect(() => {
    setError(null);
  }, [tokenFromUrl]);

  // Phase 1 Handler: Request Reset Link
  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmed = identifier.trim();
    if (!trimmed) {
      setError('Please enter your registered email address or phone number.');
      return;
    }

    setIsLoading(true);
    try {
      const res = await apiClient.post('/auth/password/reset/', {
        identifier: trimmed,
        email: trimmed,
      });

      const data = res.data;
      setRequestSuccessMessage(
        data.message || 'If an account exists with those details, password reset instructions have been dispatched.'
      );
      if (data.reset_url) {
        setDevResetUrl(data.reset_url);
      }
      setRequestSubmitted(true);
    } catch (err: any) {
      const data = err.response?.data;
      let msg = 'Failed to submit password reset request. Please check your details.';
      if (data) {
        if (typeof data.detail === 'string') {
          msg = data.detail;
        } else if (typeof data.message === 'string') {
          msg = data.message;
        } else if (data.identifier) {
          msg = Array.isArray(data.identifier) ? data.identifier.join(' ') : String(data.identifier);
        } else if (data.email) {
          msg = Array.isArray(data.email) ? data.email.join(' ') : String(data.email);
        } else if (Array.isArray(data.non_field_errors)) {
          msg = data.non_field_errors.join(' ');
        }
      }
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // Phase 2 Handler: Confirm New Password
  const handleConfirmReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!newPassword) {
      setError('Please enter a new password.');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match. Please re-enter.');
      return;
    }

    setIsLoading(true);
    try {
      await apiClient.post('/auth/password/reset/confirm/', {
        token: tokenFromUrl,
        password: newPassword,
        confirm_password: confirmPassword,
      });

      setConfirmSuccess(true);
    } catch (err: any) {
      const data = err.response?.data;
      let msg = 'Failed to reset password. The link may have expired or is invalid.';
      if (data) {
        if (typeof data.detail === 'string') {
          msg = data.detail;
        } else if (typeof data.message === 'string') {
          msg = data.message;
        } else if (data.token) {
          msg = Array.isArray(data.token) ? data.token.join(' ') : String(data.token);
        } else if (data.password) {
          msg = Array.isArray(data.password) ? data.password.join(' ') : String(data.password);
        } else if (data.confirm_password) {
          msg = Array.isArray(data.confirm_password) ? data.confirm_password.join(' ') : String(data.confirm_password);
        } else if (Array.isArray(data.non_field_errors)) {
          msg = data.non_field_errors.join(' ');
        }
      }
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background Ambient Glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-xl border border-slate-700/80 rounded-2xl shadow-2xl p-6 sm:p-8 relative z-10">
        {/* Header Icon & Title */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center shadow-xl shadow-emerald-900/40 mb-4">
            {tokenFromUrl ? (
              <KeyRound className="w-7 h-7 text-white" />
            ) : (
              <School className="w-7 h-7 text-white" />
            )}
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            {tokenFromUrl ? 'Set New Password' : 'Reset Your Password'}
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-1 max-w-xs">
            {tokenFromUrl
              ? 'Enter your new password below to regain access to your account.'
              : 'Enter your registered school email or phone number to receive reset instructions.'}
          </p>
        </div>

        {/* Global Error Banner */}
        {error && (
          <div className="mb-5 p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium flex items-start gap-2.5 animate-fadeIn">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* ================= PHASE 2: CONFIRM / SET NEW PASSWORD ================= */}
        {tokenFromUrl ? (
          confirmSuccess ? (
            <div className="text-center py-4 space-y-4 animate-fadeIn">
              <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Password Updated</h3>
                <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
                  Your password has been securely reset. You can now sign in to your SchoolBridge portal with your new password.
                </p>
              </div>

              <div className="pt-2">
                <Button
                  variant="primary"
                  size="lg"
                  className="w-full"
                  onClick={() => navigate('/auth/login')}
                >
                  Proceed to Sign In
                </Button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleConfirmReset} className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="new-password" className="text-xs font-medium text-slate-300">
                    New Password
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1 focus:outline-none"
                  >
                    {showPassword ? (
                      <>
                        <EyeOff className="w-3.5 h-3.5" /> Hide
                      </>
                    ) : (
                      <>
                        <Eye className="w-3.5 h-3.5" /> Show
                      </>
                    )}
                  </button>
                </div>
                <TextInput
                  id="new-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Min. 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  leftIcon={<Lock className="w-4 h-4 text-slate-400" />}
                  required
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="confirm-new-password" className="text-xs font-medium text-slate-300">
                  Confirm New Password
                </label>
                <TextInput
                  id="confirm-new-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Re-type your new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  leftIcon={<Lock className="w-4 h-4 text-slate-400" />}
                  required
                />
              </div>

              {/* Security Hint */}
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-700/50 text-[11px] text-slate-400 space-y-1">
                <p className="font-semibold text-slate-300">Password Requirements:</p>
                <ul className="list-disc list-inside space-y-0.5 text-slate-400">
                  <li className={newPassword.length >= 8 ? 'text-emerald-400 font-medium' : ''}>
                    At least 8 characters long
                  </li>
                  <li className={newPassword && newPassword === confirmPassword ? 'text-emerald-400 font-medium' : ''}>
                    Passwords match exactly
                  </li>
                  <li>Must differ from your last 3 passwords</li>
                </ul>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="w-full mt-2"
                isLoading={isLoading}
              >
                Set New Password
              </Button>

              <div className="text-center pt-2">
                <Link
                  to="/auth/login"
                  className="text-xs text-slate-400 hover:text-white inline-flex items-center gap-1.5 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Cancel & Back to Login
                </Link>
              </div>
            </form>
          )
        ) : (
          /* ================= PHASE 1: REQUEST RESET ================= */
          requestSubmitted ? (
            <div className="text-center py-4 space-y-4 animate-fadeIn">
              <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Reset Request Sent</h3>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                  {requestSuccessMessage}
                </p>
                <p className="text-[11px] text-slate-500 mt-1">
                  Recipient: <span className="text-emerald-400 font-medium">{identifier}</span>
                </p>
              </div>

              {/* Dev / Testing Quick Link Helper */}
              {devResetUrl && (
                <div className="p-3 bg-emerald-950/40 border border-emerald-500/40 rounded-xl text-left">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase font-bold text-emerald-400">
                      Testing / Dev Helper
                    </span>
                    <ExternalLink className="w-3.5 h-3.5 text-emerald-400" />
                  </div>
                  <p className="text-[11px] text-slate-300 mb-2">
                    A reset link was generated for testing:
                  </p>
                  <a
                    href={devResetUrl}
                    className="block text-center text-xs font-semibold py-1.5 px-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors"
                  >
                    Open Password Reset Link &rarr;
                  </a>
                </div>
              )}

              <div className="pt-3">
                <Link to="/auth/login" className="inline-block w-full">
                  <Button variant="secondary" size="md" className="w-full" leftIcon={<ArrowLeft className="w-4 h-4" />}>
                    Return to Login
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleRequestReset} className="space-y-4">
              <TextInput
                id="reset-identifier"
                label="Email or Phone Number"
                placeholder="e.g. teacher@stmarys.ug or 0771234567"
                helperText="Enter the school email or phone number associated with your teacher/staff account."
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                leftIcon={<Mail className="w-4 h-4 text-slate-400" />}
                required
                autoFocus
              />

              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="w-full mt-2"
                isLoading={isLoading}
              >
                Send Reset Link
              </Button>

              <div className="text-center pt-2">
                <Link
                  to="/auth/login"
                  className="text-xs text-slate-400 hover:text-white inline-flex items-center gap-1.5 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back to Login
                </Link>
              </div>
            </form>
          )
        )}
      </div>
    </div>
  );
};
