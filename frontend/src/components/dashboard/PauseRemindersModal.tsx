import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { apiClient } from '../../api/client';
import { PauseCircle, AlertTriangle } from 'lucide-react';

interface PauseRemindersModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (pauseData: any) => void;
}

export const PauseRemindersModal: React.FC<PauseRemindersModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('school_holiday');
  const [droppedStrategy, setDroppedStrategy] = useState('reschedule_after_pause');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!startDate || !endDate) {
      setError('Please select both start and end dates.');
      return;
    }

    if (new Date(startDate) > new Date(endDate)) {
      setError('Start date cannot be after end date.');
      return;
    }

    setIsLoading(true);
    try {
      const res = await apiClient.post('/automation/messaging-pause/', {
        start_date: startDate,
        end_date: endDate,
        reason,
      });

      onSuccess(res.data);
      onClose();
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to pause automated reminders.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Pause Automated Fee Reminders"
      description="US-064: Director-initiated messaging pause with start/end date and dropped-task policy."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
            {error}
          </div>
        )}

        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <span>
            Pausing reminders will halt all automated WhatsApp and SMS balance escalations during the specified window.
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <TextInput
            label="Pause Start Date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
          <TextInput
            label="Pause End Date"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-300 block mb-1.5">Pause Reason</label>
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="school_holiday">School Holiday / End of Term</option>
            <option value="national_exams">National UNEB Exams Period</option>
            <option value="director_discretion">Director Discretion</option>
          </select>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-300 block mb-1.5">Dropped Task Policy</label>
          <select
            value={droppedStrategy}
            onChange={(e) => setDroppedStrategy(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 text-slate-100 rounded-lg px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="reschedule_after_pause">Reschedule Reminders After Pause End</option>
            <option value="discard_dropped_tasks">Discard Dropped Reminders (Do Not Send)</option>
          </select>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="danger"
            isLoading={isLoading}
            leftIcon={<PauseCircle className="w-4 h-4" />}
          >
            Confirm Pause
          </Button>
        </div>
      </form>
    </Modal>
  );
};
