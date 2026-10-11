import React, { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { CurrencyInput } from '../ui/CurrencyInput';
import { Plus, Trash2, Save, Layers, AlertCircle } from 'lucide-react';

export interface FeeStructureItemData {
  id?: number | string;
  name: string;
  amount: number | '';
  is_mandatory: boolean;
  description?: string;
}

export interface FeeStructureData {
  id: string;
  name: string;
  class_group?: number | string;
  class_name?: string;
  academic_term?: number | string;
  term_name?: string;
  is_active?: boolean;
  total_amount?: number | string;
  items: FeeStructureItemData[];
}

interface EditFeeStructureModalProps {
  isOpen: boolean;
  onClose: () => void;
  structure: FeeStructureData | null;
  onSaved?: () => void;
}

export const EditFeeStructureModal: React.FC<EditFeeStructureModalProps> = ({
  isOpen,
  onClose,
  structure,
  onSaved,
}) => {
  const queryClient = useQueryClient();
  const [name, setName] = useState(structure?.name || '');
  const [items, setItems] = useState<FeeStructureItemData[]>(() =>
    (structure?.items || []).map((item) => ({
      id: item.id,
      name: item.name || '',
      amount: typeof item.amount === 'number' ? item.amount : Number(item.amount) || 0,
      is_mandatory: item.is_mandatory !== false,
      description: item.description || '',
    }))
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && structure) {
      setName(structure.name || '');
      setItems(
        (structure.items || []).map((item) => ({
          id: item.id,
          name: item.name || '',
          amount: typeof item.amount === 'number' ? item.amount : Number(item.amount) || 0,
          is_mandatory: item.is_mandatory !== false,
          description: item.description || '',
        }))
      );
      setError(null);
    }
  }, [isOpen, structure]);

  const handleAddItem = () => {
    setItems((prev) => [
      ...prev,
      {
        name: '',
        amount: '',
        is_mandatory: true,
        description: '',
      },
    ]);
  };

  const handleRemoveItem = (index: number) => {
    if (items.length <= 1) {
      setError('A fee structure must have at least one fee line item.');
      return;
    }
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleItemChange = (index: number, field: keyof FeeStructureItemData, value: any) => {
    setItems((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
    if (error) setError(null);
  };

  const totalAmount = items.reduce((sum, item) => {
    const amt = typeof item.amount === 'number' ? item.amount : Number(item.amount) || 0;
    return sum + amt;
  }, 0);

  const { mutate: saveStructure, isPending } = useMutation({
    mutationFn: async () => {
      if (!structure?.id) throw new Error('Structure ID missing');

      const payload = {
        name: name.trim(),
        items: items.map((item) => ({
          name: item.name.trim(),
          amount: Math.round(typeof item.amount === 'number' ? item.amount : Number(item.amount) || 0),
          is_mandatory: !!item.is_mandatory,
          description: item.description || '',
        })),
      };

      const res = await apiClient.patch(`/payments/fee-structures/${structure.id}/`, payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fee-structures'] });
      queryClient.invalidateQueries({ queryKey: ['fee-records'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
      if (onSaved) onSaved();
      onClose();
    },
    onError: (err: any) => {
      console.error('[EditFeeStructureModal] Error:', err);
      const data = err.response?.data;
      let msg = 'Failed to save fee structure. Please verify the inputs.';
      if (typeof data === 'string') {
        msg = data;
      } else if (data?.detail) {
        msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      } else if (data?.items) {
        msg = Array.isArray(data.items)
          ? data.items.map((i: any) => (typeof i === 'object' ? Object.values(i).flat().join(', ') : i)).join('; ')
          : String(data.items);
      }
      setError(msg);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Fee structure name is required.');
      return;
    }

    if (items.length === 0) {
      setError('Please add at least one fee line item.');
      return;
    }

    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (!it.name.trim()) {
        setError(`Item #${i + 1} must have a name.`);
        return;
      }
      const amt = typeof it.amount === 'number' ? it.amount : Number(it.amount);
      if (isNaN(amt) || amt <= 0) {
        setError(`Item "${it.name}" must have an amount greater than 0.`);
        return;
      }
    }

    saveStructure();
  };

  const displayName = structure?.class_name || structure?.name || 'Class Structure';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Edit Fee Structure — ${displayName}`}
      description={`Update fee items, levies, and structure total for ${displayName}`}
      maxWidth="2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Structure Overview Bar */}
        <div className="p-3.5 bg-slate-800/80 rounded-xl border border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-white">{structure?.name}</p>
              <p className="text-[10px] text-slate-400">
                Class: <span className="text-emerald-400 font-semibold">{structure?.class_name || 'All Streams'}</span>
                {structure?.term_name ? ` • Term: ${structure.term_name}` : ''}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wider">Computed Total</p>
            <p className="text-sm font-bold text-emerald-400 font-mono">
              UGX {totalAmount.toLocaleString()}
            </p>
          </div>
        </div>

        {/* Structure Name Input */}
        <TextInput
          label="Structure Name"
          placeholder="e.g. P.5 East Term 1 2026 Fees"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (error) setError(null);
          }}
          required
        />

        {/* Line Items Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                Fee Line Items ({items.length})
              </h3>
              <p className="text-[11px] text-slate-400">
                Configure all mandatory and optional charges that compose this fee structure
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5 text-emerald-400" />}
              onClick={handleAddItem}
              className="text-xs"
            >
              Add Fee Item
            </Button>
          </div>

          <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
            {items.map((item, idx) => (
              <div
                key={item.id || idx}
                className="p-3 bg-slate-850 border border-slate-750 rounded-xl space-y-2.5 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <TextInput
                      label={`Item #${idx + 1} Name`}
                      placeholder="e.g. Tuition, Lunch, Computer Lab"
                      value={item.name}
                      onChange={(e) => handleItemChange(idx, 'name', e.target.value)}
                      required
                    />
                  </div>
                  <div className="w-44">
                    <CurrencyInput
                      label="Amount (UGX)"
                      value={item.amount}
                      onChange={(val) => handleItemChange(idx, 'amount', val)}
                      currencyPrefix="UGX"
                    />
                  </div>
                  <div className="pt-5">
                    <button
                      type="button"
                      onClick={() => handleRemoveItem(idx)}
                      disabled={items.length <= 1}
                      title={items.length <= 1 ? 'At least one item required' : 'Remove fee item'}
                      className="p-2 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-slate-750 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-800">
                  <label className="flex items-center gap-2 cursor-pointer select-none text-slate-300">
                    <input
                      type="checkbox"
                      checked={item.is_mandatory}
                      onChange={(e) => handleItemChange(idx, 'is_mandatory', e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-slate-700 bg-slate-900 text-emerald-500 focus:ring-emerald-500"
                    />
                    <span className="text-[11px]">Mandatory fee item (applies to all students in class)</span>
                  </label>
                  {typeof item.amount === 'number' && item.amount > 0 && (
                    <span className="text-[11px] font-mono text-emerald-400 font-semibold">
                      UGX {item.amount.toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Total Summary Footer Box */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-750 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400">Total Structure Amount:</span>
            <p className="text-[10px] text-slate-500">
              Saving will automatically update total for this class and all associated fee records
            </p>
          </div>
          <div className="text-right">
            <span className="text-base font-bold text-emerald-400 font-mono">
              UGX {totalAmount.toLocaleString()}
            </span>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="secondary" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            isLoading={isPending}
            leftIcon={<Save className="w-4 h-4" />}
          >
            Save Fee Structure
          </Button>
        </div>
      </form>
    </Modal>
  );
};