import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { KpiCard } from '../../components/dashboard/KpiCard';
import { StatGroup } from '../../components/dashboard/StatGroup';
import { GaugeProgressChart } from '../../components/dashboard/GaugeProgressChart';
import { AreaTrendChart } from '../../components/dashboard/AreaTrendChart';
import { Button } from '../../components/ui/Button';
import { RecordPaymentModal } from '../../components/finance/RecordPaymentModal';
import { BulkReminderModal } from '../../components/finance/BulkReminderModal';
import { 
  Banknote, 
  CreditCard, 
  AlertTriangle, 
  RefreshCw, 
  Megaphone,
  ArrowRight,
  Receipt
} from 'lucide-react';

export const BursarDashboardPage: React.FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [recordPaymentOpen, setRecordPaymentOpen] = useState(false);
  const [campaignModalOpen, setCampaignModalOpen] = useState(false);
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);

  // Fetch Dashboard Overview Metrics from Backend API
  const { data: metrics, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: async () => {
      const res = await apiClient.get('/automation/dashboard/overview/');
      return res.data;
    },
    staleTime: 0,               // always re-fetch — never serve a cached/stale value
    refetchOnMount: true,       // fetch fresh every time dashboard mounts
    refetchOnWindowFocus: true, // fetch when user returns to the tab
    refetchInterval: 60_000,    // auto-refresh every 60 s while on dashboard
    retry: 1,
  });

  const handleManualRefresh = async () => {
    setIsManualRefreshing(true);
    try {
      await apiClient.get('/automation/dashboard/overview/?refresh=true');
      await refetch();
    } catch (err) {
      console.error('Failed to refresh metrics', err);
    } finally {
      setIsManualRefreshing(false);
    }
  };

  const collectionRate = metrics?.collection_rate ?? 0;
  const trendData = metrics?.trend_data || [];
  const lowClasses = metrics?.low_collection_classes || [];
  const pendingRecon = metrics?.pending_reconciliation_count || 0;
  const outstandingRevenue = metrics?.outstanding_revenue ?? Math.max(0, (metrics?.expected_revenue || 0) - (metrics?.total_revenue_collected || 0));
  const defaultersCount = metrics?.total_defaulters_count ?? metrics?.high_risk_defaulters_count ?? 0;

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Bursar Operations & Financial Dashboard
            </h1>
            <span className="text-[11px] font-semibold uppercase px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Live Operations
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time fee collections, default risk management, and mobile money reconciliation
          </p>
        </div>

        {/* Operational Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleManualRefresh}
            isLoading={isManualRefreshing || isFetching}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${isFetching || isManualRefreshing ? 'animate-spin' : ''}`} />}
            title="Refresh live metrics from database"
          >
            Refresh
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/finance/reconciliation')}
            leftIcon={<CreditCard className="w-4 h-4 text-indigo-400" />}
          >
            <span>MoMo Recon</span>
            {pendingRecon > 0 && (
              <span className="ml-1.5 px-1.5 py-0.2 bg-amber-500/20 text-amber-300 rounded text-[10px] font-bold border border-amber-500/30">
                {pendingRecon} Pending
              </span>
            )}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => setCampaignModalOpen(true)}
            leftIcon={<Megaphone className="w-4 h-4 text-emerald-400" />}
          >
            Send Reminders
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setRecordPaymentOpen(true)}
            leftIcon={<Banknote className="w-4 h-4" />}
          >
            + Record Payment
          </Button>
        </div>
      </div>

      {/* Metric Cards Grid - 4 Interactive Launchers */}
      <StatGroup>
        <KpiCard
          title="Total Revenue (UGX)"
          value={metrics?.total_revenue_collected != null ? `UGX ${Number(metrics.total_revenue_collected).toLocaleString()}` : '—'}
          change={metrics?.expected_revenue ? `${collectionRate.toFixed(1)}% of target` : ''}
          changeType="positive"
          subtitle={`Collected this term of UGX ${Number(metrics?.expected_revenue || 0).toLocaleString()} target`}
          icon={<Banknote className="w-5 h-5 text-emerald-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/finance')}
          clickableHint="View fee accounts"
        />

        <KpiCard
          title="Outstanding Fees"
          value={`UGX ${Number(outstandingRevenue).toLocaleString()}`}
          change={defaultersCount > 0 ? `${defaultersCount} defaulters` : 'Cleared'}
          changeType={defaultersCount > 0 ? 'negative' : 'positive'}
          subtitle={`${defaultersCount} students with uncollected balance`}
          icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/finance?filter=defaulter')}
          clickableHint="View defaulters"
        />

        <KpiCard
          title="Today's Collections"
          value={metrics?.today_collections_ugx != null ? `UGX ${Number(metrics.today_collections_ugx).toLocaleString()}` : 'UGX 0'}
          change={metrics?.today_payment_count ? `${metrics.today_payment_count} transactions` : '0 today'}
          changeType="neutral"
          subtitle="Cash & mobile money recorded today"
          icon={<Receipt className="w-5 h-5 text-teal-400" />}
          isLoading={isLoading}
          onClick={() => setRecordPaymentOpen(true)}
          clickableHint="Record payment"
        />

        <KpiCard
          title="Pending Reconciliation"
          value={`${pendingRecon} Items`}
          change={pendingRecon > 0 ? 'Action required' : 'All matched'}
          changeType={pendingRecon > 0 ? 'negative' : 'positive'}
          subtitle="MoMo transactions awaiting student match"
          icon={<CreditCard className="w-5 h-5 text-indigo-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/finance/reconciliation')}
          clickableHint="Reconcile now"
        />
      </StatGroup>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <AreaTrendChart 
            data={trendData} 
            title="14-Day Collection Trend"
            subtitle="Daily cash and mobile money collections over past two weeks"
          />
        </div>
        <div>
          <GaugeProgressChart percentage={collectionRate} />
          <div className="mt-3 flex items-center justify-between px-2 text-xs text-slate-400">
            <span>Collected: <strong className="text-white font-mono">UGX {((metrics?.total_revenue_collected || 0) / 1000000).toFixed(1)}M</strong></span>
            <span>Target: <strong className="text-white font-mono">UGX {((metrics?.expected_revenue || 0) / 1000000).toFixed(1)}M</strong></span>
          </div>
        </div>
      </div>

      {/* Low Collection Classes Table */}
      <div className="bg-slate-800/80 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Classes Requiring Campaign Focus
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Streams with lowest collection rates — targeted WhatsApp defaulter reminders recommended
            </p>
          </div>
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => setCampaignModalOpen(true)}
            leftIcon={<Megaphone className="w-3.5 h-3.5 text-emerald-400" />}
          >
            Launch Campaign
          </Button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 uppercase tracking-wider">
                <th className="py-3 px-4">Class Stream</th>
                <th className="py-3 px-4">Expected (UGX)</th>
                <th className="py-3 px-4">Collected (UGX)</th>
                <th className="py-3 px-4">Collection Rate</th>
                <th className="py-3 px-4 text-right">Quick Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {lowClasses.map((cls: any, idx: number) => (
                <tr key={idx} className="hover:bg-slate-700/30 transition-colors group">
                  <td className="py-3 px-4 font-semibold text-white">{cls.class_name}</td>
                  <td className="py-3 px-4 text-slate-300 font-mono">UGX {cls.expected.toLocaleString()}</td>
                  <td className="py-3 px-4 text-emerald-400 font-medium font-mono">UGX {cls.collected.toLocaleString()}</td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-1 rounded-md bg-amber-500/10 text-amber-300 font-semibold border border-amber-500/20 font-mono">
                      {cls.rate}%
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <button
                      onClick={() => navigate(`/finance?filter=defaulter`)}
                      className="text-xs text-slate-400 hover:text-emerald-400 font-medium inline-flex items-center gap-1 group-hover:underline"
                    >
                      View Defaulters <ArrowRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quick Operational Launchpad */}
      <div className="bg-slate-800/60 border border-slate-700/50 rounded-2xl p-5 shadow-lg">
        <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">
          Bursar Operational Launchpad
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <button
            onClick={() => navigate('/finance')}
            className="p-3 bg-slate-900/60 hover:bg-slate-900 border border-slate-700/60 hover:border-emerald-500/40 rounded-xl text-left transition-all group"
          >
            <span className="text-xs font-semibold text-white group-hover:text-emerald-300 flex items-center justify-between">
              Fee Accounts <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-emerald-400" />
            </span>
            <p className="text-[11px] text-slate-400 mt-1">Student balances & ledgers</p>
          </button>

          <button
            onClick={() => navigate('/finance?filter=defaulter')}
            className="p-3 bg-slate-900/60 hover:bg-slate-900 border border-slate-700/60 hover:border-rose-500/40 rounded-xl text-left transition-all group"
          >
            <span className="text-xs font-semibold text-white group-hover:text-rose-300 flex items-center justify-between">
              Defaulter Lists <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-rose-400" />
            </span>
            <p className="text-[11px] text-slate-400 mt-1">Escalated balance tracking</p>
          </button>

          <button
            onClick={() => navigate('/finance/reconciliation')}
            className="p-3 bg-slate-900/60 hover:bg-slate-900 border border-slate-700/60 hover:border-indigo-500/40 rounded-xl text-left transition-all group"
          >
            <span className="text-xs font-semibold text-white group-hover:text-indigo-300 flex items-center justify-between">
              MoMo Matching <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-indigo-400" />
            </span>
            <p className="text-[11px] text-slate-400 mt-1">Automated bank & telco recon</p>
          </button>

          <button
            onClick={() => navigate('/finance?action=end_of_day')}
            className="p-3 bg-slate-900/60 hover:bg-slate-900 border border-slate-700/60 hover:border-teal-500/40 rounded-xl text-left transition-all group"
          >
            <span className="text-xs font-semibold text-white group-hover:text-teal-300 flex items-center justify-between">
              End-of-Day Closing <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-teal-400" />
            </span>
            <p className="text-[11px] text-slate-400 mt-1">Daily reconciliation signing</p>
          </button>
        </div>
      </div>

      {/* Record Payment Modal */}
      <RecordPaymentModal
        isOpen={recordPaymentOpen}
        onClose={() => setRecordPaymentOpen(false)}
        onPaymentRecorded={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
        }}
      />

      {/* Bulk Reminder Campaign Modal */}
      <BulkReminderModal
        isOpen={campaignModalOpen}
        onClose={() => setCampaignModalOpen(false)}
        onSent={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
        }}
      />
    </div>
  );
};
