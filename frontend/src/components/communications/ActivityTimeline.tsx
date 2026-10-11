import React from 'react';
import {
  MessageSquare,
  PhoneCall,
  ArrowUpRight,
  ArrowDownLeft,
  AlertTriangle,
  RotateCw,
  CheckCircle2,
  Clock,
  Zap,
} from 'lucide-react';
import { Badge } from '../ui/Badge';
import type { BadgeVariant } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface TimelineLog {
  id: string;
  recipient_phone: string;
  recipient_name?: string;
  student_name?: string;
  channel: 'whatsapp' | 'sms' | 'voice';
  channel_display?: string;
  direction: 'outbound' | 'inbound';
  message_body: string;
  status: 'delivered' | 'sent' | 'failed' | 'received' | 'queued' | 'read';
  template_type?: string;
  template_type_display?: string;
  is_fallback?: boolean;
  fallback_triggered_at?: string;
  fallback_status?: 'delivered' | 'sent' | 'failed' | null;
  fallback_log_id?: string | null;
  has_fallback?: boolean;
  error_message?: string;
  timestamp: string;
  delivered_at?: string;
}

interface ActivityTimelineProps {
  logs: TimelineLog[];
  isLoading?: boolean;
  onRetry?: (logId: string, channel: 'sms' | 'whatsapp') => void;
  retryingId?: string | null;
}

const statusVariant = (status: TimelineLog['status']): BadgeVariant => {
  if (status === 'delivered' || status === 'read') return 'success';
  if (status === 'sent') return 'info';
  if (status === 'failed') return 'danger';
  if (status === 'queued') return 'neutral';
  return 'warning';
};

const formatTemplateType = (type?: string): string => {
  if (!type) return 'Message';
  const map: Record<string, string> = {
    payment_receipt: 'Payment Receipt',
    fee_reminder: 'Fee Reminder',
    broadcast: 'Broadcast Campaign',
    absence_alert: 'Absence Alert',
    voice_broadcast: 'Voice Call',
    balance_response: 'Balance Inquiry',
    receipt_response: 'Receipt Request',
  };
  return map[type] || type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const getEffectiveFallback = (log: TimelineLog, allLogs: TimelineLog[]) => {
  // 1. Direct field from backend serializer
  if (log.fallback_status) {
    return {
      status: log.fallback_status,
      logId: log.fallback_log_id,
      delivered: log.fallback_status === 'delivered',
    };
  }

  // 2. If log itself was retried/failed-over to SMS and delivered
  if (log.is_fallback && log.status === 'delivered') {
    return {
      status: 'delivered',
      logId: log.id,
      delivered: true,
    };
  }

  // 3. Companion search in allLogs in memory
  if (log.channel === 'whatsapp' && log.status === 'failed') {
    const cleanPhone = log.recipient_phone.replace(/\D/g, '');
    const logTime = new Date(log.timestamp).getTime();

    const companion = allLogs.find((other) => {
      if (other.id === log.id) return false;
      if (!other.is_fallback && other.channel !== 'sms') return false;
      const otherPhone = other.recipient_phone.replace(/\D/g, '');
      if (cleanPhone && otherPhone && cleanPhone !== otherPhone) return false;
      if (log.template_type && other.template_type && log.template_type !== other.template_type) return false;

      const otherTime = new Date(other.timestamp).getTime();
      const diff = otherTime - logTime;
      return diff >= -120_000 && diff <= 86_400_000;
    });

    if (companion) {
      return {
        status: companion.status,
        logId: companion.id,
        delivered: companion.status === 'delivered',
      };
    }
  }

  return null;
};

export const ActivityTimeline: React.FC<ActivityTimelineProps> = ({
  logs,
  isLoading = false,
  onRetry,
  retryingId,
}) => {
  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-20 bg-slate-800/60 rounded-2xl border border-slate-700/40" />
        ))}
      </div>
    );
  }

  if (!logs || logs.length === 0) {
    return (
      <div className="p-12 bg-slate-800/40 border border-slate-700/60 rounded-2xl text-center space-y-2">
        <div className="w-12 h-12 rounded-full bg-slate-700/50 flex items-center justify-center text-slate-400 mx-auto">
          <MessageSquare className="w-6 h-6" />
        </div>
        <p className="text-sm font-semibold text-slate-300">No message logs found</p>
        <p className="text-xs text-slate-400">
          Try adjusting your search criteria, timeframe, or channel filters above.
        </p>
      </div>
    );
  }

  return (
    <div className="relative border-l-2 border-slate-700/80 ml-4 space-y-6">
      {logs.map((log) => {
        const isFailed = log.status === 'failed';
        const isRetrying = retryingId === log.id;
        const fallback = getEffectiveFallback(log, logs);
        const isRecoveredByFallback = Boolean(
          isFailed &&
          (fallback?.delivered || fallback?.status === 'sent' || log.has_fallback)
        );
        const isFailoverDelivered = fallback?.delivered ?? (isRecoveredByFallback && fallback?.status !== 'sent');

        return (
          <div key={log.id} className="relative pl-6 group">
            {/* Timeline Node Icon */}
            <div
              className={`absolute -left-[17px] top-2 w-8 h-8 rounded-full border-2 flex items-center justify-center transition-all ${
                isRecoveredByFallback
                  ? 'bg-emerald-950/90 border-emerald-500/70 text-emerald-400 shadow-sm shadow-emerald-950'
                  : isFailed
                  ? 'bg-rose-950/80 border-rose-500/60 text-rose-400 shadow-sm shadow-rose-950'
                  : log.channel === 'voice'
                  ? 'bg-indigo-950/80 border-indigo-500/60 text-indigo-400'
                  : log.channel === 'sms'
                  ? 'bg-amber-950/80 border-amber-500/60 text-amber-400'
                  : 'bg-emerald-950/80 border-emerald-500/60 text-emerald-400'
              }`}
            >
              {isRecoveredByFallback ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              ) : log.channel === 'voice' ? (
                <PhoneCall className="w-3.5 h-3.5" />
              ) : (
                <MessageSquare className="w-3.5 h-3.5" />
              )}
            </div>

            {/* Timeline Card */}
            <div
              className={`bg-slate-800/90 backdrop-blur-md border rounded-2xl p-4.5 space-y-3 shadow-lg transition-all ${
                isRecoveredByFallback
                  ? 'border-emerald-500/40 hover:border-emerald-500/60 bg-gradient-to-r from-emerald-950/15 via-slate-800/90 to-slate-800/90'
                  : isFailed
                  ? 'border-rose-500/30 hover:border-rose-500/50 bg-gradient-to-r from-rose-950/10 to-slate-800/90'
                  : 'border-slate-700/70 hover:border-slate-600'
              }`}
            >
              {/* Header row: Recipient + Channel Badges + Status + Timestamp */}
              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-white font-mono tracking-tight">
                    {log.recipient_phone}
                  </span>
                  {(log.recipient_name || log.student_name) && (
                    <span className="text-xs text-slate-300 font-medium">
                      ({log.recipient_name || log.student_name})
                    </span>
                  )}

                  {/* Channel Tag */}
                  {log.channel === 'voice' ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                      <PhoneCall className="w-2.5 h-2.5" />
                      Voice Call
                    </span>
                  ) : log.channel === 'sms' ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                      <Zap className="w-2.5 h-2.5" />
                      {log.is_fallback ? 'SMS Failover' : 'SMS'}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                      <MessageSquare className="w-2.5 h-2.5" />
                      WhatsApp
                    </span>
                  )}

                  {/* Recovered failover tag */}
                  {isRecoveredByFallback && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                      <Zap className="w-2.5 h-2.5 text-amber-400" />
                      Carrier Failover
                    </span>
                  )}

                  {/* Message Type Badge */}
                  {log.template_type && (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-300 border border-slate-600/40">
                      {formatTemplateType(log.template_type)}
                    </span>
                  )}

                  {log.direction === 'outbound' ? (
                    <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <ArrowDownLeft className="w-3.5 h-3.5 text-indigo-400" />
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {isRecoveredByFallback ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-sm">
                      <Zap className="w-3 h-3 text-amber-400" />
                      {isFailoverDelivered ? 'SMS FAILOVER DELIVERED' : 'SMS FAILOVER SENT'}
                    </span>
                  ) : (
                    <Badge variant={statusVariant(log.status)} size="sm">
                      {log.status.toUpperCase()}
                    </Badge>
                  )}
                  <span className="text-[11px] text-slate-400 font-mono flex items-center gap-1">
                    <Clock className="w-3 h-3 text-slate-500" />
                    {new Date(log.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}{' '}
                    • {new Date(log.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                  </span>
                </div>
              </div>

              {/* Message Body Content */}
              <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-700/40 text-xs text-slate-200 font-mono whitespace-pre-wrap break-words leading-relaxed">
                {log.message_body || (
                  <span className="text-slate-500 italic">No message body recorded</span>
                )}
              </div>

              {/* Failure Alert Box & Actions - Only when NOT recovered */}
              {isFailed && !isRecoveredByFallback && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-rose-950/30 border border-rose-500/30 rounded-xl">
                  <div className="flex items-start gap-2 text-rose-300 text-xs">
                    <AlertTriangle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-semibold text-rose-200">Delivery Incomplete</p>
                      <p className="text-[11px] text-rose-300/80">
                        {log.error_message ||
                          'Handset unreachable or API timeout. Failover to direct SMS available.'}
                      </p>
                    </div>
                  </div>

                  {onRetry && (
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={isRetrying}
                        onClick={() => onRetry(log.id, 'sms')}
                        leftIcon={
                          isRetrying ? (
                            <RotateCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Zap className="w-3.5 h-3.5 text-amber-400" />
                          )
                        }
                        className="bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/40 text-xs py-1"
                      >
                        {isRetrying ? 'Retrying…' : 'Retry via SMS Failover'}
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* Failover Recovery Box - when WhatsApp failed but was recovered via SMS */}
              {isFailed && isRecoveredByFallback && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-emerald-950/25 border border-emerald-500/30 rounded-xl">
                  <div className="flex items-start gap-2.5 text-emerald-300 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-emerald-200">
                          {isFailoverDelivered ? 'Recovered via Automated SMS Failover' : 'SMS Failover In-Flight'}
                        </p>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium">
                          Auto-Recovered
                        </span>
                      </div>
                      <p className="text-[11px] text-emerald-300/85 mt-0.5">
                        WhatsApp message encountered delivery timeout ({log.error_message || 'Handset offline'}), but automated SMS fallback routed immediately to {log.recipient_phone} and was confirmed.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Successful SMS Fallback note for the companion SMS card */}
              {log.is_fallback && log.status === 'delivered' && !isFailed && (
                <div className="flex items-center gap-2 text-[11px] text-emerald-400/90 bg-emerald-950/20 border border-emerald-500/20 px-3 py-1.5 rounded-lg">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Delivered via automated SMS fallback after WhatsApp timeout</span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

