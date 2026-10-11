import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { UgandaPhoneInput } from '../../components/ui/UgandaPhoneInput';
import {
  School,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Clock,
  Lock,
  ArrowRight,
  PhoneCall,
  FileCheck,
  Zap,
} from 'lucide-react';
import { detectUgandaTelecom, getTelecomNetworkInfo, validateUgandaPhone } from '../../utils/telecom';

interface PaymentLinkData {
  token: string;
  amount: number;
  description: string;
  status: string;
  is_usable: boolean;
  expires_at: string;
  student_name: string;
  student_code: string;
  class_name: string;
  school_name: string;
  recipient_phone: string;
}

export const PublicPaymentPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const [phone, setPhone] = useState('');
  const [provider, setProvider] = useState<'mtn_momo' | 'airtel_money'>('mtn_momo');
  const [paymentSuccess, setPaymentSuccess] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Auto-detect network info for display
  const detectedNetwork = getTelecomNetworkInfo(phone);

  const handlePhoneChange = (newVal: string) => {
    setPhone(newVal);
    const detected = detectUgandaTelecom(newVal);
    if (detected) {
      setProvider(detected);
    }
  };

  // Fetch link details
  const { data: linkData, isLoading, isError } = useQuery<PaymentLinkData>({
    queryKey: ['public-payment-link', token],
    queryFn: async () => {
      const res = await apiClient.get(`/payments/payment-links/public/${token}/`);
      return res.data;
    },
    enabled: !!token,
    retry: false,
  });

  // Auto-fill phone and auto-detect provider when data loads
  React.useEffect(() => {
    if (linkData?.recipient_phone && !phone) {
      const initialPhone = linkData.recipient_phone;
      setPhone(initialPhone);
      const detected = detectUgandaTelecom(initialPhone);
      if (detected) {
        setProvider(detected);
      }
    }
  }, [linkData, phone]);

  // Submit payment mutation
  const { mutate: submitPayment, isPending } = useMutation({
    mutationFn: async () => {
      const phoneVal = validateUgandaPhone(phone);
      const res = await apiClient.post(`/payments/payment-links/public/${token}/pay/`, {
        phone: phoneVal.isValid ? phoneVal.international : phone.trim(),
        provider,
      });
      return res.data;
    },
    onSuccess: (data) => {
      setPaymentSuccess(data);
    },
    onError: (err: any) => {
      const data = err.response?.data;
      const msg =
        (typeof data?.detail === 'string' ? data.detail : null) ||
        (typeof data?.error === 'string' ? data.error : null) ||
        (Array.isArray(data?.detail) ? data.detail.join(', ') : null) ||
        'Payment processing failed. Please verify your phone number and try again.';
      setError(msg);
    },
  });

  const handlePay = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const phoneVal = validateUgandaPhone(phone);
    if (!phoneVal.isValid) {
      setError(phoneVal.error || 'Please enter a valid 10-digit Ugandan phone number (e.g. 0771234567).');
      return;
    }
    submitPayment();
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-12 h-12 border-4 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin mx-auto" />
          <p className="text-xs text-slate-400 font-medium">Loading secure payment portal...</p>
        </div>
      </div>
    );
  }

  if (isError || !linkData) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 text-center space-y-4 shadow-2xl">
          <div className="w-14 h-14 bg-rose-500/10 border border-rose-500/30 rounded-2xl flex items-center justify-center mx-auto text-rose-400">
            <AlertCircle className="w-8 h-8" />
          </div>
          <h2 className="text-lg font-bold text-white">Payment Link Expired or Invalid</h2>
          <p className="text-xs text-slate-400 leading-relaxed">
            This payment link is either expired, already used, or invalid. Please request a new payment link from your school's bursar.
          </p>
          <div className="pt-2">
            <Link to="/auth/login">
              <Button variant="secondary" size="sm">
                Return to SchoolBridge Portal
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 sm:p-6 text-slate-100">
      {/* Glow Effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md bg-slate-900/90 backdrop-blur-xl border border-slate-800 rounded-3xl shadow-2xl overflow-hidden relative z-10">
        {/* Top Header */}
        <div className="bg-gradient-to-r from-emerald-950/60 to-slate-900 p-6 border-b border-slate-800 text-center relative">
          <div className="w-12 h-12 bg-gradient-to-tr from-emerald-600 to-teal-500 rounded-2xl flex items-center justify-center mx-auto shadow-lg shadow-emerald-950/50 mb-3">
            <School className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-base font-bold text-white tracking-tight">{linkData.school_name}</h1>
          <p className="text-[11px] text-emerald-400 font-medium flex items-center justify-center gap-1 mt-0.5">
            <ShieldCheck className="w-3.5 h-3.5" /> Official Fee Collection Gateway
          </p>
        </div>

        {/* Success Confirmation Screen */}
        {paymentSuccess ? (
          <div className="p-6 text-center space-y-5">
            <div className="w-16 h-16 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl flex items-center justify-center mx-auto text-emerald-400">
              <CheckCircle2 className="w-10 h-10" />
            </div>

            <div>
              <h3 className="text-lg font-bold text-white">Payment Received!</h3>
              <p className="text-xs text-slate-400 mt-1">
                Receipt #{paymentSuccess.receipt_number} has been generated and sent to {phone}.
              </p>
            </div>

            <div className="p-4 bg-slate-800/80 rounded-2xl border border-slate-700/80 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Student:</span>
                <span className="font-semibold text-white">{linkData.student_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Registration ID:</span>
                <span className="font-mono text-emerald-400">{linkData.student_code}</span>
              </div>
              <div className="flex justify-between border-t border-slate-700 pt-2 font-bold text-sm">
                <span className="text-white">Amount Paid:</span>
                <span className="text-emerald-400">UGX {Number(linkData.amount).toLocaleString()}</span>
              </div>
            </div>

            <div className="p-3 bg-emerald-500/10 rounded-xl border border-emerald-500/20 text-[11px] text-emerald-300 flex items-center gap-2 text-left">
              <FileCheck className="w-5 h-5 shrink-0 text-emerald-400" />
              <span>An official electronic receipt has been registered to the school's ledger.</span>
            </div>
          </div>
        ) : (
          /* Payment Form Screen */
          <form onSubmit={handlePay} className="p-6 space-y-5">
            {error && (
              <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium">
                {error}
              </div>
            )}

            {/* Student & Fee Summary Card */}
            <div className="p-4 bg-slate-800/80 rounded-2xl border border-slate-700/80 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Student Details</p>
                  <p className="text-sm font-bold text-white mt-0.5">{linkData.student_name}</p>
                  <p className="text-[11px] font-mono text-emerald-400">
                    {linkData.student_code} • {linkData.class_name}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Amount</p>
                  <p className="text-base font-bold text-emerald-400">
                    UGX {Number(linkData.amount).toLocaleString()}
                  </p>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-700/60 flex items-center justify-between text-[11px] text-slate-400">
                <span>{linkData.description}</span>
                <span className="flex items-center gap-1 text-amber-400/90 font-mono text-[10px]">
                  <Clock className="w-3 h-3" /> Valid for 72h
                </span>
              </div>
            </div>

            {/* Provider Selection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300 block">
                  Select Mobile Money Network
                </label>
                {detectedNetwork && (
                  <span
                    className={`inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md border animate-fadeIn ${detectedNetwork.badgeBg} ${detectedNetwork.badgeText} ${detectedNetwork.badgeBorder}`}
                  >
                    <Zap className="w-3 h-3 text-current animate-pulse" />
                    Auto-detected: {detectedNetwork.shortName}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setProvider('mtn_momo')}
                  className={`p-3 rounded-xl border flex flex-col items-center gap-1 transition-all ${
                    provider === 'mtn_momo'
                      ? 'border-yellow-500 bg-yellow-500/15 text-yellow-400 font-bold shadow-lg shadow-yellow-950/40 ring-1 ring-yellow-500/50'
                      : 'border-slate-800 bg-slate-900/50 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    {provider === 'mtn_momo' && <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />}
                    <span className="text-xs font-bold">MTN MoMo</span>
                  </div>
                  <span className="text-[9px] opacity-75">*165# Prompt</span>
                </button>

                <button
                  type="button"
                  onClick={() => setProvider('airtel_money')}
                  className={`p-3 rounded-xl border flex flex-col items-center gap-1 transition-all ${
                    provider === 'airtel_money'
                      ? 'border-rose-500 bg-rose-500/15 text-rose-400 font-bold shadow-lg shadow-rose-950/40 ring-1 ring-rose-500/50'
                      : 'border-slate-800 bg-slate-900/50 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    {provider === 'airtel_money' && <span className="w-2 h-2 rounded-full bg-rose-400 animate-pulse" />}
                    <span className="text-xs font-bold">Airtel Money</span>
                  </div>
                  <span className="text-[9px] opacity-75">*185# Prompt</span>
                </button>
              </div>
            </div>

            {/* Phone Number Input */}
            <div className="space-y-1">
              <UgandaPhoneInput
                label="Payer Phone Number"
                placeholder="e.g. 0770 000 000 or 0700 000 000"
                value={phone}
                onChange={(e) => handlePhoneChange(e.target.value)}
                onNetworkDetected={(net) => setProvider(net)}
                required
              />
              <p className="text-[10px] text-slate-400 flex items-center gap-1 mt-1">
                <PhoneCall className="w-3 h-3 text-emerald-400" />
                You will receive a USSD push on this phone to enter your MoMo PIN.
              </p>
            </div>

            {/* Submit Action */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full font-bold shadow-xl shadow-emerald-950/50"
              isLoading={isPending}
              rightIcon={<ArrowRight className="w-4 h-4" />}
            >
              Pay UGX {Number(linkData.amount).toLocaleString()}
            </Button>

            {/* Security Footer */}
            <div className="pt-2 text-center text-[10px] text-slate-500 flex items-center justify-center gap-1 border-t border-slate-800/80">
              <Lock className="w-3 h-3 text-emerald-500/70" />
              <span>Bank-Grade 256-bit Encrypted • Bank of Uganda Regulated</span>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
