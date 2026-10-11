import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { CurrencyInput } from '../ui/CurrencyInput';
import { TextInput } from '../ui/TextInput';
import { Link2, Copy, Check, MessageSquare } from 'lucide-react';

interface PaymentLinkModalProps {
  isOpen: boolean;
  onClose: () => void;
  feeRecordId?: string;
  studentId: string;
  studentCode?: string;
  className?: string;
  studentName: string;
  defaultAmount?: number;
}

export const PaymentLinkModal: React.FC<PaymentLinkModalProps> = ({
  isOpen,
  onClose,
  feeRecordId,
  studentId,
  studentCode,
  className,
  studentName,
  defaultAmount = 0,
}) => {
  const [amount, setAmount] = useState<number>(defaultAmount);
  const [description, setDescription] = useState('Term Fee Payment Link');
  const [generatedLink, setGeneratedLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync amount with defaultAmount prop when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setAmount(defaultAmount);
      setGeneratedLink(null);
      setError(null);
    }
  }, [isOpen, defaultAmount]);

  const { mutate: generateLink, isPending } = useMutation({
    mutationFn: async () => {
      const payload = {
        fee_record_id: feeRecordId,
        student_id: studentId,
        amount,
        description,
        expiry_hours: 72,
      };
      const res = await apiClient.post('/payments/payment-links/generate/', payload);
      return res.data;
    },
    onSuccess: (data) => {
      const fullUrl = data.payment_url || data.link || '';
      if (!fullUrl) {
        setError('Payment link was generated but no URL was returned. Contact support.');
        return;
      }
      setGeneratedLink(fullUrl);
    },
    onError: (err: any) => {
      const data = err.response?.data;
      const msg =
        (typeof data?.detail === 'string' ? data.detail : null) ||
        (typeof data?.error === 'string' ? data.error : null) ||
        (err.response?.status === 404 ? 'Payment link generation is not yet configured on this server. Please contact your system administrator.' : null) ||
        'Failed to generate payment link.';
      setError(msg);
    },
  });

  const handleCopy = () => {
    if (generatedLink) {
      navigator.clipboard.writeText(generatedLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (amount <= 0) {
      setError('Amount must be greater than zero.');
      return;
    }
    generateLink();
  };

  const handleModalClose = () => {
    setGeneratedLink(null);
    setError(null);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleModalClose}
      title="Generate MoMo Payment Link"
      description="US-C03: Create a secure 64-char token payment link with 72-hour expiry"
      maxWidth="lg"
    >
      <div className="space-y-4">
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
            {error}
          </div>
        )}

        <div className="p-3.5 bg-slate-800 rounded-xl border border-slate-700 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-white">{studentName}</p>
            <p className="text-[10px] font-mono text-emerald-400">
              {studentCode || studentId} {className ? `• ${className}` : ''}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wider">Amount Due</p>
            <p className="text-xs font-bold text-white">UGX {Number(amount).toLocaleString()}</p>
          </div>
        </div>

        {generatedLink ? (
          <div className="space-y-4 py-2">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-center space-y-2">
              <Link2 className="w-8 h-8 text-emerald-400 mx-auto" />
              <h4 className="text-sm font-bold text-white">Payment Link Ready</h4>
              <p className="text-xs text-slate-300 font-mono break-all bg-slate-900 p-2 rounded border border-slate-700">
                {generatedLink}
              </p>
              <p className="text-[10px] text-slate-400">Valid for 72 hours from generation</p>
            </div>

            <div className="flex gap-3">
              <Button
                variant="secondary"
                size="md"
                className="flex-1"
                leftIcon={copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                onClick={handleCopy}
              >
                {copied ? 'Link Copied!' : 'Copy Payment Link'}
              </Button>
              <a
                href={`https://wa.me/?text=${encodeURIComponent(`SchoolBridge Fee Payment Link for ${studentName}: ${generatedLink}`)}`}
                target="_blank"
                rel="noreferrer"
                className="flex-1"
              >
                <Button
                  variant="primary"
                  size="md"
                  className="w-full"
                  leftIcon={<MessageSquare className="w-4 h-4" />}
                >
                  Send via WhatsApp
                </Button>
              </a>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <CurrencyInput
              label="Link Payment Target (UGX)"
              value={amount}
              onChange={(val) => setAmount(val)}
              required
            />

            <TextInput
              label="Description / Purpose"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
              <Button type="button" variant="secondary" onClick={handleModalClose}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                isLoading={isPending}
                leftIcon={<Link2 className="w-4 h-4" />}
              >
                Generate 72h Payment Link
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
};
