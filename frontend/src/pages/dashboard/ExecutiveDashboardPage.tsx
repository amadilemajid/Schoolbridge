import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { KpiCard } from '../../components/dashboard/KpiCard';
import { StatGroup } from '../../components/dashboard/StatGroup';
import { GaugeProgressChart } from '../../components/dashboard/GaugeProgressChart';
import { AreaTrendChart } from '../../components/dashboard/AreaTrendChart';
import { AlertBanner } from '../../components/ui/AlertBanner';
import { Button } from '../../components/ui/Button';
import { PauseRemindersModal } from '../../components/dashboard/PauseRemindersModal';
import { BulkReminderModal } from '../../components/finance/BulkReminderModal';
import { ApprovalQueueBanner } from '../../components/finance/ApprovalQueueBanner';
import { ReviewWaiversModal } from '../../components/finance/ReviewWaiversModal';
import { useRbac } from '../../hooks/useRbac';
import { useAuth } from '../../context/AuthContext';
import { 
  Banknote, 
  Users, 
  AlertTriangle, 
  CalendarCheck, 
  PauseCircle, 
  PlayCircle,
  Megaphone,
  RefreshCw,
  ArrowRight
} from 'lucide-react';

export const ExecutiveDashboardPage: React.FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { can } = useRbac();
  const { user } = useAuth();
  const isDirector = user?.role === 'director' || user?.role === 'system_admin';
  const canPauseMessaging = can('messaging:pause');

  const [pauseModalOpen, setPauseModalOpen] = useState(false);
  const [campaignModalOpen, setCampaignModalOpen] = useState(false);
  const [reviewWaiversOpen, setReviewWaiversOpen] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // ── Direct fetch — bypasses ALL React Query caching ──────────────────────
  const [metrics, setMetrics] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMetrics = useCallback(async (bustCache = false) => {
    setIsFetching(true);
    try {
      const token = localStorage.getItem('schoolbridge_access_token');
      const schoolId = localStorage.getItem('schoolbridge_active_school_id');
      const ts = Date.now(); // cache-bust query param
      const url = bustCache
        ? `/api/v1/automation/dashboard/overview/?refresh=true&_ts=${ts}`
        : `/api/v1/automation/dashboard/overview/?_ts=${ts}`;
      const res = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(schoolId ? { 'X-School-ID': schoolId } : {}),
        },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMetrics(data);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('[Dashboard] Metrics fetch error:', err);
    } finally {
      setIsLoading(false);
      setIsFetching(false);
    }
  }, []);

  // Fetch on mount, then every 30 s
  useEffect(() => {
    fetchMetrics(false);
    intervalRef.current = setInterval(() => fetchMetrics(false), 30_000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchMetrics]);

  // Re-fetch when window regains focus
  useEffect(() => {
    const onFocus = () => fetchMetrics(false);
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [fetchMetrics]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await fetchMetrics(true);
    setIsRefreshing(false);
  };

  const pauseActive = Boolean(metrics?.messaging_paused);
  const pauseDetails = metrics?.active_pause;

  const handleResumeReminders = async () => {
    setIsResuming(true);
    try {
      if (pauseDetails?.id) {
        await apiClient.post(`/automation/messaging-pause/${pauseDetails.id}/end/`);
      } else {
        const res = await apiClient.get('/automation/messaging-pause/');
        const pauses = res.data?.results || res.data || [];
        const active = pauses.find((p: any) => p.is_active);
        if (active?.id) {
          await apiClient.post(`/automation/messaging-pause/${active.id}/end/`);
        }
      }
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
    } catch (err) {
      console.error('Failed to resume reminders', err);
    } finally {
      setIsResuming(false);
    }
  };

  const collectionRate = metrics?.collection_rate ?? 0;
  const trendData = metrics?.trend_data || [];
  const lowClasses = metrics?.low_collection_classes || [];
  const defaultersCount = metrics?.total_defaulters_count ?? metrics?.high_risk_defaulters_count ?? 0;

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Executive Operational Dashboard
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time financial, attendance, and default risk metrics
            {lastUpdated && (
              <span className="ml-2 px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono">
                Live · {lastUpdated.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleManualRefresh}
            isLoading={isRefreshing || isFetching}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${isFetching || isRefreshing ? 'animate-spin' : ''}`} />}
            title="Refresh metrics from backend"
          >
            Refresh
          </Button>

          {canPauseMessaging && (
            <Button
              variant={pauseActive ? 'secondary' : 'danger'}
              size="sm"
              onClick={() => setPauseModalOpen(true)}
              leftIcon={pauseActive ? <PlayCircle className="w-4 h-4 text-emerald-400" /> : <PauseCircle className="w-4 h-4" />}
            >
              {pauseActive ? 'Messaging Paused' : 'Pause Reminders'}
            </Button>
          )}
        </div>
      </div>

      {/* Active Messaging Pause Warning Banner */}
      {pauseActive && (
        <AlertBanner
          type="warning"
          title="Director Messaging Pause Active"
          message={`Automated balance reminders are paused from ${pauseDetails?.start_date || 'Today'} to ${pauseDetails?.end_date || 'End Date'}. Reason: ${pauseDetails?.reason || 'School Holiday'}.`}
          actionButton={
            <Button size="sm" variant="ghost" isLoading={isResuming} onClick={handleResumeReminders}>
              Resume Reminders Now
            </Button>
          }
        />
      )}

      {/* ── Director Approval Queue: Pending Waivers & High-Value Payments ── */}
      <ApprovalQueueBanner
        isDirector={isDirector}
        onPaymentApproved={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
        }}
        onWaiverApproved={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
        }}
        onOpenWaiversModal={() => setReviewWaiversOpen(true)}
      />

      {/* Metric Cards Grid - Interactive Drill-Downs */}
      <StatGroup>
        <KpiCard
          title="Total Revenue (UGX)"
          value={metrics?.total_revenue_collected != null ? `UGX ${Number(metrics.total_revenue_collected).toLocaleString()}` : '—'}
          change={metrics?.expected_revenue ? `${collectionRate.toFixed(1)}% of target` : ''}
          changeType="positive"
          subtitle={`Collected of UGX ${Number(metrics?.expected_revenue || 0).toLocaleString()} target`}
          icon={<Banknote className="w-5 h-5 text-emerald-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/finance')}
          clickableHint="View fee accounts"
        />

        <KpiCard
          title="Active Enrolment"
          value={metrics?.active_students ?? '—'}
          change=""
          changeType="positive"
          subtitle="Enrolled students in school"
          icon={<Users className="w-5 h-5 text-indigo-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/students')}
          clickableHint="View student directory"
        />

        <KpiCard
          title="Today's Attendance"
          value={metrics?.attendance_rate_today != null ? `${metrics.attendance_rate_today}%` : '—'}
          change=""
          changeType="positive"
          subtitle="School attendance rate today"
          icon={<CalendarCheck className="w-5 h-5 text-teal-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/attendance')}
          clickableHint="View attendance"
        />

        <KpiCard
          title="High Default Risk"
          value={defaultersCount}
          change={defaultersCount > 0 ? 'Requires action' : 'Cleared'}
          changeType={defaultersCount > 0 ? 'negative' : 'positive'}
          subtitle={`${defaultersCount} students with outstanding fees`}
          icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
          isLoading={isLoading}
          onClick={() => navigate('/finance?filter=defaulter')}
          clickableHint="View defaulters"
        />
      </StatGroup>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <AreaTrendChart data={trendData} />
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
              Targeted WhatsApp defaulter campaigns recommended
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

      {/* Pause Reminders Modal */}
      <PauseRemindersModal
        isOpen={pauseModalOpen}
        onClose={() => setPauseModalOpen(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
        }}
      />

      {/* Campaign Modal */}
      <BulkReminderModal
        isOpen={campaignModalOpen}
        onClose={() => setCampaignModalOpen(false)}
        onSent={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
        }}
      />

      {/* Review Waivers Modal */}
      <ReviewWaiversModal
        isOpen={reviewWaiversOpen}
        onClose={() => setReviewWaiversOpen(false)}
        isDirector={isDirector}
        onWaiverApproved={() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
          queryClient.invalidateQueries({ queryKey: ['approval-queue-waivers'] });
        }}
      />
    </div>
  );
};
