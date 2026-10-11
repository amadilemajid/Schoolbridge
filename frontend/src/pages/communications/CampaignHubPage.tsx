import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { StatGroup } from '../../components/dashboard/StatGroup';
import { KpiCard } from '../../components/dashboard/KpiCard';
import { ActivityTimeline } from '../../components/communications/ActivityTimeline';
import type { TimelineLog } from '../../components/communications/ActivityTimeline';
import { CampaignBuilderModal } from '../../components/communications/CampaignBuilderModal';
import { WhatsAppSimulatorModal } from '../../components/communications/WhatsAppSimulatorModal';
import { Button } from '../../components/ui/Button';
import { FilterBar } from '../../components/ui/FilterBar';
import {
  Send,
  CheckCircle2,
  PhoneCall,
  Smartphone,
  AlertTriangle,
  Zap,
  RotateCw,
  Calendar,
} from 'lucide-react';

interface MessagingKpi {
  total_sent: number;
  total_delivered: number;
  total_failed: number;
  unrecovered_failed?: number;
  total_in_flight: number;
  delivery_rate_pct: number;
  sms_fallbacks: number;
  total_inbound: number;
  by_channel: {
    whatsapp: number;
    sms: number;
    voice: number;
  };
  payments_collected_ugx: number;
  timeframe: string;
  channel: string;
}

export const CampaignHubPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [campaignModalOpen, setCampaignModalOpen] = useState(false);
  const [simulatorModalOpen, setSimulatorModalOpen] = useState(false);

  // Filters & State
  const [search, setSearch] = useState('');
  const [channelFilter, setChannelFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [templateFilter, setTemplateFilter] = useState('');
  const [timeframe, setTimeframe] = useState<'all' | 'today' | '7d' | 'term'>('all');
  const [retryingLogId, setRetryingLogId] = useState<string | null>(null);
  const [bannerNotice, setBannerNotice] = useState<string | null>(null);

  // 1. Live KPI Query — fully reactive to channel and timeframe filters
  const { data: kpi, isLoading: kpiLoading } = useQuery<MessagingKpi>({
    queryKey: ['messaging-kpi', channelFilter, timeframe, statusFilter],
    queryFn: async () => {
      const params: Record<string, any> = { timeframe };
      if (channelFilter) params.channel = channelFilter;
      if (statusFilter) params.status = statusFilter;
      const res = await apiClient.get('/messaging/kpi/', { params });
      return res.data;
    },
    staleTime: 5_000,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });

  // 2. Message Audit Logs Query — with full backend filtering
  const { data: logsData, isLoading: logsLoading } = useQuery({
    queryKey: ['campaign-logs', search, channelFilter, statusFilter, templateFilter, timeframe],
    queryFn: async () => {
      const params: Record<string, any> = { timeframe };
      if (search) params.search = search;
      if (channelFilter) params.channel = channelFilter;
      if (statusFilter) params.status = statusFilter;
      if (templateFilter) params.template_type = templateFilter;

      const res = await apiClient.get('/messaging/logs/', { params });
      return res.data?.results || res.data || [];
    },
    staleTime: 5_000,
    refetchInterval: 10_000,
  });

  const logs: TimelineLog[] = Array.isArray(logsData) ? logsData : [];

  // 3. Single Log Retry Mutation
  const { mutate: retryLog } = useMutation({
    mutationFn: async ({ logId, channel }: { logId: string; channel: 'sms' | 'whatsapp' }) => {
      setRetryingLogId(logId);
      const res = await apiClient.post(`/messaging/logs/${logId}/retry/`, { channel });
      return res.data;
    },
    onSuccess: (data) => {
      setRetryingLogId(null);
      setBannerNotice(data.message || 'Message retried successfully via SMS failover.');
      queryClient.invalidateQueries({ queryKey: ['campaign-logs'] });
      queryClient.invalidateQueries({ queryKey: ['messaging-kpi'] });
      setTimeout(() => setBannerNotice(null), 5000);
    },
    onError: (err: any) => {
      setRetryingLogId(null);
      alert(err.response?.data?.error || 'Failed to retry message.');
    },
  });

  // 4. Bulk Retry All Failed Mutation
  const { mutate: retryAllFailed, isPending: isRetryingAll } = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/messaging/logs/retry-all/', { channel: 'sms' });
      return res.data;
    },
    onSuccess: (data) => {
      setBannerNotice(data.message || 'Successfully triggered bulk SMS failover for all failed messages.');
      queryClient.invalidateQueries({ queryKey: ['campaign-logs'] });
      queryClient.invalidateQueries({ queryKey: ['messaging-kpi'] });
      setTimeout(() => setBannerNotice(null), 6000);
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || 'Failed to trigger bulk failover.');
    },
  });

  const handleResetFilters = () => {
    setSearch('');
    setChannelFilter('');
    setStatusFilter('');
    setTemplateFilter('');
    setTimeframe('all');
  };

  const failedCount = kpi?.unrecovered_failed ?? 0;
  const totalFailed = kpi?.total_failed ?? 0;

  return (
    <div className="space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            WhatsApp & Communications Hub
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time delivery telemetry, multi-channel broadcast engine & automated failovers
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Smartphone className="w-4 h-4 text-emerald-400" />}
            onClick={() => setSimulatorModalOpen(true)}
            className="border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10"
          >
            Launch Simulator
          </Button>

          <Button
            variant="primary"
            size="sm"
            leftIcon={<Send className="w-4 h-4" />}
            onClick={() => setCampaignModalOpen(true)}
          >
            + New Campaign
          </Button>
        </div>
      </div>

      {/* Timeframe Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-800/60 border border-slate-700/60 p-2.5 rounded-2xl">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 px-2">
          <Calendar className="w-3.5 h-3.5 text-emerald-400" />
          <span>Telemetry Window:</span>
        </div>

        <div className="flex items-center gap-1.5 bg-slate-900/80 p-1 rounded-xl border border-slate-700/50">
          {(
            [
              { key: 'today', label: 'Today' },
              { key: '7d', label: 'Last 7 Days' },
              { key: 'term', label: 'This Term' },
              { key: 'all', label: 'All Time' },
            ] as const
          ).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTimeframe(t.key)}
              className={`px-3 py-1 text-xs font-medium rounded-lg transition-all ${
                timeframe === t.key
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Dynamic KPI Cards — Click to filter */}
      <StatGroup>
        <KpiCard
          title="Messages Sent"
          value={(kpi?.total_sent ?? 0).toLocaleString()}
          change={
            kpi
              ? `${kpi.by_channel?.whatsapp ?? 0} WA • ${kpi.by_channel?.voice ?? 0} Voice • ${kpi.by_channel?.sms ?? 0} SMS`
              : 'Live telemetry active'
          }
          changeType={kpi && kpi.total_sent > 0 ? 'positive' : 'neutral'}
          isLoading={kpiLoading}
          icon={<Send className="w-5 h-5 text-emerald-400" />}
          isActive={statusFilter === '' && !channelFilter}
          onClick={() => {
            setStatusFilter('');
            setChannelFilter('');
          }}
          clickableHint="All messages"
        />

        <KpiCard
          title="Delivery Success Rate"
          value={kpi ? `${kpi.delivery_rate_pct}%` : '0%'}
          change={
            kpi?.total_delivered
              ? `${kpi.total_delivered.toLocaleString()} confirmed delivered`
              : kpi?.total_sent
              ? 'Processing deliveries'
              : 'No broadcasts in window'
          }
          changeType={kpi && kpi.delivery_rate_pct >= 85 ? 'positive' : 'neutral'}
          isLoading={kpiLoading}
          icon={<CheckCircle2 className="w-5 h-5 text-teal-400" />}
          isActive={statusFilter === 'delivered'}
          onClick={() => setStatusFilter('delivered')}
          clickableHint="Filter delivered"
        />

        <KpiCard
          title="Failed Deliveries"
          value={totalFailed.toLocaleString()}
          change={
            failedCount > 0
              ? `${failedCount} action required (SMS Failover)`
              : totalFailed > 0
              ? 'All failures auto-recovered via SMS failover'
              : 'Zero failures — healthy'
          }
          changeType={failedCount > 0 ? 'negative' : 'positive'}
          isLoading={kpiLoading}
          icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
          isActive={statusFilter === 'failed'}
          onClick={() => setStatusFilter('failed')}
          clickableHint="Filter failed"
        />

        <KpiCard
          title="SMS Fallbacks & Inbound"
          value={(kpi?.sms_fallbacks ?? 0).toLocaleString()}
          change={
            kpi?.total_inbound
              ? `${kpi.total_inbound} parent replies handled`
              : 'Carrier failover ready'
          }
          changeType="neutral"
          isLoading={kpiLoading}
          icon={<PhoneCall className="w-5 h-5 text-amber-400" />}
          isActive={channelFilter === 'sms'}
          onClick={() => setChannelFilter('sms')}
          clickableHint="Filter SMS"
        />
      </StatGroup>

      {/* Action Banner: 1-Click Bulk Failover */}
      {failedCount > 0 && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl bg-gradient-to-r from-rose-950/40 via-slate-800/80 to-amber-950/30 border border-rose-500/30 shadow-lg animate-in fade-in">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">
                {failedCount} Undelivered Message{failedCount > 1 ? 's' : ''} Detected
              </p>
              <p className="text-xs text-slate-300 mt-0.5">
                Handsets were offline or carrier timed out. You can trigger automated SMS failover to guarantee immediate delivery.
              </p>
            </div>
          </div>

          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={isRetryingAll}
            onClick={() => retryAllFailed()}
            leftIcon={
              isRetryingAll ? (
                <RotateCw className="w-4 h-4 animate-spin text-amber-400" />
              ) : (
                <Zap className="w-4 h-4 text-amber-400" />
              )
            }
            className="bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border-amber-500/40 whitespace-nowrap shrink-0 shadow-sm"
          >
            {isRetryingAll ? 'Dispatching SMS Failover…' : '⚡ 1-Click SMS Failover (Retry All)'}
          </Button>
        </div>
      )}

      {/* Success Notification Banner */}
      {bannerNotice && (
        <div className="p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{bannerNotice}</span>
        </div>
      )}

      {/* Filter Bar with Multi-Criteria Selectors */}
      <FilterBar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder="Search message logs by phone, recipient, or text body…"
        onResetAll={handleResetFilters}
      >
        {/* Channel Dropdown */}
        <select
          value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
          aria-label="Filter by delivery channel"
        >
          <option value="">All Channels</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="sms">SMS Fallback</option>
          <option value="voice">Voice Broadcast</option>
        </select>

        {/* Status Dropdown */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
          aria-label="Filter by delivery status"
        >
          <option value="">All Statuses</option>
          <option value="delivered">Delivered</option>
          <option value="failed">Failed / Undelivered</option>
          <option value="sent">Sent / Pending</option>
        </select>

        {/* Message Type Dropdown */}
        <select
          value={templateFilter}
          onChange={(e) => setTemplateFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
          aria-label="Filter by template type"
        >
          <option value="">All Message Types</option>
          <option value="payment_receipt">Payment Receipts</option>
          <option value="fee_reminder">Fee Reminders</option>
          <option value="broadcast">Broadcasts</option>
          <option value="absence_alert">Absence Alerts</option>
        </select>
      </FilterBar>

      {/* Active Filter Indicators */}
      {(channelFilter || statusFilter || templateFilter || search || timeframe !== 'all') && (
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
          <span className="text-slate-400">Active Filters:</span>
          {channelFilter && (
            <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-200">
              Channel: <b className="text-emerald-400 uppercase">{channelFilter}</b>
            </span>
          )}
          {statusFilter && (
            <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-200">
              Status: <b className="text-amber-400 uppercase">{statusFilter}</b>
            </span>
          )}
          {templateFilter && (
            <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-200">
              Type: <b className="text-indigo-400">{templateFilter.replace(/_/g, ' ')}</b>
            </span>
          )}
          {timeframe !== 'all' && (
            <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-200">
              Window: <b className="text-cyan-400">{timeframe}</b>
            </span>
          )}
          <button
            type="button"
            onClick={handleResetFilters}
            className="text-xs text-rose-400 hover:underline ml-1"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Timeline Section */}
      <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Real-Time Delivery Audit Trail ({logs.length} entries)
          </h3>
          <span className="text-[11px] text-slate-500 font-mono">
            Auto-refreshing every 10s
          </span>
        </div>

        <ActivityTimeline
          logs={logs}
          isLoading={logsLoading}
          onRetry={(logId, ch) => retryLog({ logId, channel: ch })}
          retryingId={retryingLogId}
        />
      </div>

      {/* Campaign Builder Modal */}
      <CampaignBuilderModal
        isOpen={campaignModalOpen}
        onClose={() => setCampaignModalOpen(false)}
      />

      {/* WhatsApp Simulator Modal */}
      <WhatsAppSimulatorModal
        isOpen={simulatorModalOpen}
        onClose={() => setSimulatorModalOpen(false)}
      />
    </div>
  );
};
