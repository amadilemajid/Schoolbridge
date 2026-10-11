/**
 * CampaignBuilderModal — General Broadcast Campaign Builder
 *
 * Supports:
 *  1. Delivery Channels: WhatsApp, SMS, Voice Call (via dropdown)
 *  2. Voice Broadcast (.mp3/.wav/.ogg/.m4a upload with instant client validation, rejecting .exe)
 *  3. Live recipient preview via /messaging/broadcasts/preview/
 *  4. Direct submission to /messaging/broadcasts/ or /messaging/voice-broadcasts/
 *  5. Dynamic real-time feedback with zero hardcoded values
 */
import React, { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { Select } from '../ui/Select';
import {
  Send, AlertCircle, CheckCircle2, Users, Eye, Loader2,
  FileAudio, UploadCloud, Trash2, Volume2,
} from 'lucide-react';

interface CampaignBuilderModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ClassOption {
  id: string;
  name: string;
}

interface PreviewResult {
  count: number;
  target_type: string;
  channel: string;
  sample: Array<{ phone: string; student_id: string }>;
}

const TARGET_OPTIONS = [
  { value: 'all_parents', label: 'All Parents' },
  { value: 'fee_defaulters', label: 'Fee Defaulters' },
  { value: 'fully_paid', label: 'Fully Paid Students' },
  { value: 'class', label: 'Specific Class / Stream' },
];

const CHANNEL_OPTIONS = [
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'sms', label: 'SMS' },
  { value: 'voice', label: 'Voice Call' },
];

const DEFAULT_MESSAGES: Record<string, string> = {
  all_parents:
    'Dear {parent_name}, this is an important notice from {school_name}. Please check the school portal for updates or contact the office for assistance.',
  fee_defaulters:
    'Dear {parent_name}, your child {student_name} (Class {class_name}) has an outstanding fee balance of UGX {balance}. Please clear this to avoid disruption. Reply BALANCE for your account details.',
  fully_paid:
    'Dear {parent_name}, thank you for clearing fees for {student_name}. We appreciate your commitment to your child\'s education at {school_name}.',
  class:
    'Dear {parent_name}, this is a message to parents of {class_name} students at {school_name}. Please contact the class teacher for more information.',
};

export const CampaignBuilderModal: React.FC<CampaignBuilderModalProps> = ({
  isOpen,
  onClose,
}) => {
  const queryClient = useQueryClient();

  const [title, setTitle] = useState('');
  const [targetType, setTargetType] = useState('all_parents');
  const [targetClassId, setTargetClassId] = useState('');
  const [channel, setChannel] = useState('whatsapp');
  const [messageBody, setMessageBody] = useState(DEFAULT_MESSAGES.all_parents);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [previewRequested, setPreviewRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ count: number; title: string; channel: string } | null>(null);

  // Cleanup object URL on unmount or file change
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setTitle('');
      setTargetType('all_parents');
      setTargetClassId('');
      setChannel('whatsapp');
      setMessageBody(DEFAULT_MESSAGES.all_parents);
      setAudioFile(null);
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
        setAudioUrl(null);
      }
      setPreviewRequested(false);
      setError(null);
      setSuccess(null);
    }
  }, [isOpen]);

  // Update message template when target changes
  const handleTargetChange = (val: string) => {
    setTargetType(val);
    setMessageBody(DEFAULT_MESSAGES[val] || DEFAULT_MESSAGES.all_parents);
    setPreviewRequested(false);
  };

  // Handle Audio File Selection with strict format validation
  const handleAudioSelect = (file: File) => {
    setError(null);
    const validExtensions = ['.mp3', '.ogg', '.wav', '.m4a', '.aac', '.flac', '.opus'];
    const fileName = file.name.toLowerCase();
    const hasValidExt = validExtensions.some((ext) => fileName.endsWith(ext));

    if (!hasValidExt || fileName.endsWith('.exe')) {
      setError(`Rejected: "${file.name}" is not a valid audio file. Only audio formats (.mp3, .wav, .ogg, .m4a) are supported.`);
      setAudioFile(null);
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
        setAudioUrl(null);
      }
      return;
    }

    if (file.size > 16 * 1024 * 1024) {
      setError(`Audio file is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum allowed size is 16MB.`);
      return;
    }

    setAudioFile(file);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(URL.createObjectURL(file));
  };

  // Fetch class list
  const { data: classesData } = useQuery<ClassOption[]>({
    queryKey: ['class-groups-list'],
    queryFn: async () => {
      const res = await apiClient.get('/students/classes/');
      const raw = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      return raw.map((c: any) => ({ id: String(c.id), name: c.name || c.display_name || c.full_name || 'Unknown' }));
    },
    enabled: isOpen,
    staleTime: 300_000,
  });
  const classOptions = (classesData || []).map((c) => ({ value: c.id, label: c.name }));

  // Live recipient preview
  const previewParams = {
    target_type: targetType,
    channel,
    ...(targetType === 'class' && targetClassId ? { target_class: targetClassId } : {}),
  };

  const {
    data: preview,
    isLoading: previewLoading,
    isFetching: previewFetching,
    refetch: refetchPreview,
    error: previewError,
  } = useQuery<PreviewResult>({
    queryKey: ['broadcast-preview', targetType, targetClassId, channel],
    queryFn: async () => {
      const res = await apiClient.get('/messaging/broadcasts/preview/', { params: previewParams });
      return res.data;
    },
    enabled: isOpen && previewRequested,
    staleTime: 60_000,
    retry: 0,
  });

  const handlePreviewClick = () => {
    setPreviewRequested(true);
    if (previewRequested) {
      refetchPreview();
    }
  };

  // Tag validation: only enforce {student_name} + {balance} for fee_defaulters when text message
  const requiresTags = channel !== 'voice' && targetType === 'fee_defaulters';
  const hasStudentTag = messageBody.includes('{student_name}');
  const hasBalanceTag = messageBody.includes('{balance}');
  const tagsValid = !requiresTags || (hasStudentTag && hasBalanceTag);

  // Create & Send campaign mutation
  const { mutate: launchCampaign, isPending } = useMutation({
    mutationFn: async () => {
      if (channel === 'voice') {
        if (!audioFile) {
          throw new Error('Please select an audio file for Voice Broadcast.');
        }
        const formData = new FormData();
        formData.append('audio_file', audioFile);
        formData.append('target_type', targetType);
        if (targetType === 'class' && targetClassId) {
          formData.append('target_class', targetClassId);
        }
        formData.append('description', title.trim() || 'Voice Broadcast');

        const res = await apiClient.post('/messaging/voice-broadcasts/', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        return {
          ...res.data,
          title: title.trim() || 'Voice Broadcast',
          total_recipients: preview?.count ?? 0,
          channel: 'Voice Call',
        };
      }

      const payload: Record<string, any> = {
        title: title.trim() || `Campaign – ${new Date().toLocaleDateString('en-UG')}`,
        message_body: messageBody,
        target_type: targetType,
        channel,
        send_now: true,
      };
      if (targetType === 'class' && targetClassId) {
        payload.target_class = targetClassId;
      }
      const res = await apiClient.post('/messaging/broadcasts/', payload);
      return {
        ...res.data,
        channel: channel.toUpperCase(),
      };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['campaign-logs'] });
      queryClient.invalidateQueries({ queryKey: ['messaging-kpi'] });
      setSuccess({
        count: data.total_recipients ?? preview?.count ?? 0,
        title: data.title || title || 'Broadcast Campaign',
        channel: data.channel || channel.toUpperCase(),
      });
    },
    onError: (err: any) => {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        err.response?.data?.non_field_errors?.[0] ||
        err.message ||
        'Failed to dispatch campaign. Please try again.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (channel === 'voice') {
      if (!audioFile) {
        setError('Please upload an audio file (.mp3, .wav, .ogg, .m4a) to send a voice broadcast.');
        return;
      }
    } else {
      if (!tagsValid) {
        setError('Message body must contain {student_name} and {balance} when targeting fee defaulters.');
        return;
      }
    }

    if (targetType === 'class' && !targetClassId) {
      setError('Please select a class to target.');
      return;
    }

    launchCampaign();
  };

  if (success) {
    return (
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title="Campaign Dispatched!"
        maxWidth="md"
      >
        <div className="flex flex-col items-center py-6 gap-4 text-center">
          <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
            <CheckCircle2 className="w-8 h-8 text-emerald-400" />
          </div>
          <p className="text-white font-semibold text-lg">{success.title}</p>
          <p className="text-slate-400 text-sm">
            Dispatched to <span className="text-emerald-400 font-bold">{success.count.toLocaleString()}</span> recipients via {success.channel}.
            Delivery is queued and actively processing.
          </p>
          <Button variant="primary" onClick={onClose} className="mt-2">
            Done
          </Button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New Campaign"
      description="Create and send a broadcast message or voice call to parents and students"
      maxWidth="xl"
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex gap-2 items-start">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Title */}
        <TextInput
          label="Campaign Title"
          placeholder="e.g. Term 1 Fee Reminder, School Opening Notice"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Target Audience */}
          <Select
            label="Target Audience"
            options={TARGET_OPTIONS}
            value={targetType}
            onChange={(e) => handleTargetChange(e.target.value)}
          />

          {/* Delivery Channel Dropdown */}
          <Select
            label="Delivery Channel"
            options={CHANNEL_OPTIONS}
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              setError(null);
              setPreviewRequested(false);
            }}
          />
        </div>

        {/* Target Class (conditional) */}
        {targetType === 'class' && (
          <Select
            label="Select Class / Stream"
            options={[{ value: '', label: 'Choose a class…' }, ...classOptions]}
            value={targetClassId}
            onChange={(e) => setTargetClassId(e.target.value)}
          />
        )}

        {/* Voice Audio Upload OR Message Body */}
        {channel === 'voice' ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-slate-300 flex items-center gap-1.5">
                <FileAudio className="w-4 h-4 text-emerald-400" />
                <span>Voice Audio File</span>
              </label>
              <span className="text-[10px] text-slate-400">Accepted: .mp3, .wav, .ogg, .m4a (Max 16MB)</span>
            </div>

            {!audioFile ? (
              <label
                htmlFor="voice-broadcast-file-input"
                className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-slate-700 hover:border-emerald-500/60 rounded-2xl bg-slate-800/40 hover:bg-slate-800/70 transition-all cursor-pointer group"
              >
                <input
                  id="voice-broadcast-file-input"
                  type="file"
                  accept="audio/*,.mp3,.wav,.ogg,.m4a,.aac,.flac,.opus"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleAudioSelect(file);
                    e.target.value = '';
                  }}
                />
                <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mb-2 group-hover:scale-110 transition-transform">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <p className="text-sm font-semibold text-slate-200">
                  Click to select audio file or drag & drop
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Upload .mp3 audio file for automated voice broadcast
                </p>
              </label>
            ) : (
              <div className="rounded-2xl border border-slate-700 bg-slate-800/90 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
                      <Volume2 className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white truncate max-w-[280px]">
                        {audioFile.name}
                      </p>
                      <p className="text-xs text-slate-400">
                        {(audioFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for voice broadcast
                      </p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setAudioFile(null);
                      if (audioUrl) {
                        URL.revokeObjectURL(audioUrl);
                        setAudioUrl(null);
                      }
                    }}
                    leftIcon={<Trash2 className="w-3.5 h-3.5 text-rose-400" />}
                    className="text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
                  >
                    Remove
                  </Button>
                </div>

                {audioUrl && (
                  <audio
                    controls
                    src={audioUrl}
                    className="w-full h-10 rounded-lg accent-emerald-500"
                  />
                )}
              </div>
            )}
          </div>
        ) : (
          /* Message Body */
          <div>
            <label className="text-sm font-medium text-slate-300 block mb-1.5">
              Message Body
            </label>
            <textarea
              rows={5}
              value={messageBody}
              onChange={(e) => setMessageBody(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 text-slate-100 placeholder-slate-500 rounded-xl p-3 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500"
              required
            />
            <div className="flex flex-wrap items-center justify-between text-[10px] text-slate-400 mt-1.5 gap-1">
              <span className="flex flex-wrap gap-1">
                {['{parent_name}', '{student_name}', '{balance}', '{class_name}', '{school_name}'].map((tag) => (
                  <code
                    key={tag}
                    className="text-emerald-400 bg-emerald-500/10 px-1 py-0.5 rounded cursor-pointer hover:bg-emerald-500/20"
                    onClick={() => setMessageBody((b) => b + ' ' + tag)}
                    title="Click to insert tag"
                  >
                    {tag}
                  </code>
                ))}
              </span>
              {requiresTags && (
                <span className={`font-semibold flex items-center gap-1 ${tagsValid ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {tagsValid ? (
                    <><CheckCircle2 className="w-3 h-3" /> Required tags present</>
                  ) : (
                    <><AlertCircle className="w-3 h-3" /> Missing {'{student_name}'} or {'{balance}'}</>
                  )}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Preview Recipients */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/60 p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 text-indigo-400" />
              Recipient Preview
            </span>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handlePreviewClick}
              isLoading={previewLoading || previewFetching}
              leftIcon={<Eye className="w-3.5 h-3.5" />}
            >
              {previewRequested ? 'Refresh Count' : 'Preview Recipients'}
            </Button>
          </div>

          {!previewRequested && (
            <p className="text-slate-500 text-xs">
              Click "Preview Recipients" to verify how many parents will receive this campaign.
            </p>
          )}

          {previewRequested && (previewLoading || previewFetching) && (
            <div className="flex items-center gap-2 text-slate-400 text-xs">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Calculating recipients…
            </div>
          )}

          {previewRequested && previewError && (
            <p className="text-rose-400 text-xs">Could not load preview. Check your connection.</p>
          )}

          {previewRequested && preview && !previewLoading && (
            <div>
              <p className="text-white font-bold text-lg">
                {preview.count.toLocaleString()}{' '}
                <span className="text-sm font-normal text-slate-400">confirmed recipients</span>
              </p>
              {preview.sample.length > 0 && (
                <div className="mt-2 space-y-1">
                  <p className="text-[10px] text-slate-500 uppercase font-semibold">Sample (masked)</p>
                  {preview.sample.map((s, i) => (
                    <p key={i} className="text-xs text-slate-400 font-mono">{s.phone}</p>
                  ))}
                  {preview.count > preview.sample.length && (
                    <p className="text-[10px] text-slate-500">
                      …and {(preview.count - preview.sample.length).toLocaleString()} more
                    </p>
                  )}
                </div>
              )}
              {preview.count === 0 && (
                <p className="text-amber-400 text-xs mt-1">
                  No recipients match this target. Check your filters or ensure students are enrolled.
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            isLoading={isPending}
            disabled={
              (channel === 'voice' && !audioFile) ||
              (channel !== 'voice' && !tagsValid) ||
              (targetType === 'class' && !targetClassId)
            }
            leftIcon={<Send className="w-4 h-4" />}
          >
            {channel === 'voice' ? 'Queue Voice Broadcast' : 'Send Campaign'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
