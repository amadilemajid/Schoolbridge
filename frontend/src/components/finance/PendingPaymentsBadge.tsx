import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Clock } from 'lucide-react';

interface PendingPaymentsBadgeProps {
  onClick?: () => void;
  isDirector?: boolean;
}

export const PendingPaymentsBadge: React.FC<PendingPaymentsBadgeProps> = ({ onClick, isDirector }) => {
  const { data: pendingCount = 0 } = useQuery({
    queryKey: ['pending-payments-queue-count'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/payments/payments/', { params: { status: 'pending' } });
        const data = res.data?.results || res.data || [];
        return Array.isArray(data) ? data.filter((p: any) => p.status === 'pending').length : 0;
      } catch {
        return 0;
      }
    },
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
  });

  const count = typeof pendingCount === 'number' ? pendingCount : 0;

  if (!count || count <= 0) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full text-xs font-semibold text-amber-400 hover:bg-amber-500/20 transition-colors cursor-pointer"
      title={`${count} payment${count > 1 ? 's' : ''} (> UGX 500,000) awaiting Director authorization`}
    >
      <Clock className="w-3.5 h-3.5 text-amber-400" />
      {count} Payment{count > 1 ? 's' : ''} {isDirector ? 'Awaiting Approval' : 'Pending Sign-off'}
    </button>
  );
};
