import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Button } from '../ui/Button';
import { TextInput } from '../ui/TextInput';
import { EditFeeStructureModal } from './EditFeeStructureModal';
import type { FeeStructureData } from './EditFeeStructureModal';
import {
  Layers,
  Search,
  Edit3,
  AlertCircle,
} from 'lucide-react';

interface FeeStructuresTabProps {
  onSuccessToast?: (title: string, message: string) => void;
}

export const FeeStructuresTab: React.FC<FeeStructuresTabProps> = ({ onSuccessToast }) => {
  const [search, setSearch] = useState('');
  const [selectedStructure, setSelectedStructure] = useState<FeeStructureData | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [levelFilter, setLevelFilter] = useState('all');
  const [applyingId, setApplyingId] = useState<string | null>(null);

  const { data: structures = [], isLoading, refetch } = useQuery<FeeStructureData[]>({
    queryKey: ['fee-structures'],
    queryFn: async () => {
      const res = await apiClient.get('/payments/fee-structures/');
      return Array.isArray(res.data) ? res.data : (res.data?.results || []);
    },
    staleTime: 60 * 1000,
  });

  const filteredStructures = structures.filter((st) => {
    const q = search.toLowerCase().trim();
    const nameMatch = st.name.toLowerCase().includes(q);
    const classMatch = (st.class_name || '').toLowerCase().includes(q);
    const itemMatch = (st.items || []).some((item) => item.name.toLowerCase().includes(q));
    const matchesSearch = !q || nameMatch || classMatch || itemMatch;

    if (!matchesSearch) return false;

    if (levelFilter === 'primary') {
      const cls = (st.class_name || st.name).toLowerCase();
      return cls.includes('p.') || cls.includes('primary') || cls.includes('baby') || cls.includes('nursery') || cls.includes('top');
    }
    if (levelFilter === 'secondary_o') {
      const cls = (st.class_name || st.name).toLowerCase();
      return cls.includes('s.1') || cls.includes('s.2') || cls.includes('s.3') || cls.includes('s.4') || cls.includes('senior 1') || cls.includes('senior 2') || cls.includes('senior 3') || cls.includes('senior 4');
    }
    if (levelFilter === 'secondary_a') {
      const cls = (st.class_name || st.name).toLowerCase();
      return cls.includes('s.5') || cls.includes('s.6') || cls.includes('senior 5') || cls.includes('senior 6');
    }

    return true;
  });

  const handleEdit = (structure: FeeStructureData) => {
    setSelectedStructure(structure);
    setEditModalOpen(true);
  };

  const handleApplyToStudents = async (structure: FeeStructureData) => {
    if (!window.confirm(`Apply fee structure '${structure.class_name || structure.name}' to all active enrolled students in this class?`)) {
      return;
    }
    setApplyingId(structure.id);
    try {
      const res = await apiClient.post(`/payments/fee-structures/${structure.id}/apply-to-students/`);
      if (onSuccessToast) {
        onSuccessToast(
          'Fees Applied',
          res.data?.message || `Successfully billed students.`
        );
      }
      refetch();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to apply fee structure to students.');
    } finally {
      setApplyingId(null);
    }
  };

  const handleSaved = () => {
    refetch();
    if (onSuccessToast) {
      onSuccessToast(
        'Fee Structure Saved',
        `Updated line items and total for ${selectedStructure?.class_name || selectedStructure?.name || 'structure'}.`
      );
    }
  };

  return (
    <div className="space-y-5">
      {/* Search and Filter Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-850 p-3.5 rounded-xl border border-slate-750">
        <div className="relative flex-1 max-w-md">
          <TextInput
            placeholder="Search fee structures by class, stream or item (e.g. P.5 East, Computer Lab)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            leftIcon={<Search className="w-4 h-4 text-slate-400" />}
          />
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-900 border border-slate-700/80 rounded-lg p-0.5 text-xs">
            {[
              { key: 'all', label: 'All Levels' },
              { key: 'primary', label: 'Primary' },
              { key: 'secondary_o', label: 'O-Level (S1-S4)' },
              { key: 'secondary_a', label: 'A-Level (S5-S6)' },
            ].map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setLevelFilter(tab.key)}
                className={`px-3 py-1.5 rounded-md font-medium transition-all ${
                  levelFilter === tab.key
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <span className="text-xs text-slate-400 pl-2">
            Showing <strong className="text-white">{filteredStructures.length}</strong> structures
          </span>
        </div>
      </div>

      {/* Content Area */}
      {isLoading ? (
        <div className="p-12 text-center text-slate-400 text-sm animate-pulse flex flex-col items-center gap-2">
          <Layers className="w-6 h-6 animate-spin text-emerald-400" />
          <span>Loading fee structures from server...</span>
        </div>
      ) : filteredStructures.length === 0 ? (
        <div className="p-12 text-center bg-slate-850 rounded-2xl border border-slate-750 border-dashed space-y-3">
          <AlertCircle className="w-8 h-8 text-slate-500 mx-auto" />
          <p className="text-sm font-semibold text-slate-300">
            {search ? `No fee structures matching "${search}"` : 'No fee structures found'}
          </p>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Fee structures define the mandatory and optional levies charged per class group each term.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredStructures.map((structure) => {
            const numTotal = Number(structure.total_amount) || 0;
            const items = structure.items || [];
            const mandatoryCount = items.filter((i) => i.is_mandatory !== false).length;

            return (
              <div
                key={structure.id}
                className="bg-slate-850 border border-slate-750 hover:border-slate-650 rounded-2xl p-4 flex flex-col justify-between transition-all hover:shadow-lg space-y-4"
              >
                <div>
                  {/* Top Header */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-0.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold rounded-lg font-mono">
                          {structure.class_name || 'Class Structure'}
                        </span>
                        {structure.term_name && (
                          <span className="text-[11px] text-slate-400 font-medium">
                            {structure.term_name}
                          </span>
                        )}
                      </div>
                      <h3 className="text-sm font-bold text-white tracking-tight pt-0.5">
                        {structure.name}
                      </h3>
                    </div>

                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      leftIcon={<Edit3 className="w-3.5 h-3.5 text-emerald-400" />}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleEdit(structure);
                      }}
                      className="text-xs shrink-0 cursor-pointer"
                      title={`Edit ${structure.class_name || structure.name}`}
                    >
                      Edit
                    </Button>
                  </div>

                  {/* Total Amount Pill */}
                  <div className="mt-3 p-2.5 bg-slate-900/80 rounded-xl border border-slate-750 flex items-center justify-between">
                    <span className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                      Total Fees
                    </span>
                    <span className="text-sm font-bold text-emerald-400 font-mono">
                      UGX {numTotal.toLocaleString()}
                    </span>
                  </div>

                  {/* Line Items Breakdown */}
                  <div className="mt-3 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span>Line Items ({items.length})</span>
                      <span>{mandatoryCount} mandatory</span>
                    </div>

                    <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                      {items.map((it, idx) => {
                        const itAmt = Number(it.amount) || 0;
                        return (
                          <div
                            key={it.id || idx}
                            className="flex items-center justify-between text-xs px-2.5 py-1.5 bg-slate-800/60 rounded-lg border border-slate-750/50"
                          >
                            <span className="text-slate-300 flex items-center gap-1.5">
                              <span className="text-[10px] text-slate-500 font-mono">#{idx + 1}</span>
                              <span className="font-medium text-white">{it.name}</span>
                              {it.is_mandatory && (
                                <span className="text-[9px] px-1 py-0.2 bg-slate-700 text-slate-300 rounded font-semibold">
                                  Required
                                </span>
                              )}
                            </span>
                            <span className="font-mono text-slate-300 font-semibold text-[11px]">
                              UGX {itAmt.toLocaleString()}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Card Footer info */}
                <div className="pt-3 border-t border-slate-750 flex items-center justify-between text-[11px] text-slate-500">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleApplyToStudents(structure);
                    }}
                    disabled={applyingId === structure.id}
                    className="text-amber-400 hover:text-amber-300 font-semibold cursor-pointer disabled:opacity-50 flex items-center gap-1 hover:underline"
                  >
                    {applyingId === structure.id ? 'Applying...' : 'Apply to Class'}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEdit(structure);
                    }}
                    className="text-emerald-400 hover:text-emerald-300 font-semibold hover:underline cursor-pointer"
                  >
                    Configure Line Items &rarr;
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Edit Structure Modal */}
      {editModalOpen && selectedStructure && (
        <EditFeeStructureModal
          key={selectedStructure.id}
          isOpen={editModalOpen}
          onClose={() => {
            setEditModalOpen(false);
            setSelectedStructure(null);
          }}
          structure={selectedStructure}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
};