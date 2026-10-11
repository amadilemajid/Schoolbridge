import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { ShieldAlert } from 'lucide-react';

export const PendingWaiversBadge: React.FC<{ onClick?: () => void }> = ({ onClick }) => {
  const { data: pendingCount = 0 } = useQuery({
    queryKey: ['pending-waivers-count'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/payments/waivers/', { params: { status: 'pending', page_size: 100 } });
        const data = res.data.results || res.data;
        return Array.isArray(data) ? data.filter((w: any) => w.status === 'pending').length : 0;
      } catch {
        return 0;
      }
    },
    refetchInterval: 15000,
    refetchOnWindowFocus: false,
    retry: false,
  });

  const count = typeof pendingCount === 'number' ? pendingCount : 0;

  if (!count || count <= 0) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full text-xs font-semibold text-amber-400 hover:bg-amber-500/20 transition-colors cursor-pointer"
    >
      <ShieldAlert className="w-3.5 h-3.5" />
      {count} Waiver{count > 1 ? 's' : ''} Pending Approval
    </button>
  );
};
