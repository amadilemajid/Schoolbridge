import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FileDropzone } from '../ui/FileDropzone';
import { AlertBanner } from '../ui/AlertBanner';
import { Upload, AlertTriangle, CheckCircle2, Download } from 'lucide-react';

interface ValidationError {
  row: number;
  field: string;
  value: string;
  error: string;
  fixed?: string;
}

interface CsvImportModalProps {
  isOpen: boolean;
  onClose: () => void;
}


export const CsvImportModal: React.FC<CsvImportModalProps> = ({
  isOpen,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);
  const [step, setStep] = useState<'upload' | 'validating' | 'errors' | 'success'>('upload');
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false);

  const handleDownloadTemplate = async () => {
    setIsDownloadingTemplate(true);
    try {
      const res = await apiClient.get('/students/import/template/', {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'student_import_template.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download template', err);
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const { mutate: uploadCsv, isPending } = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await apiClient.post('/students/import/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      setStep('success');
    },
    onError: (err: any) => {
      const data = err.response?.data;
      if (data?.errors) {
        setValidationErrors(data.errors);
        setStep('errors');
      }
    },
  });

  const handleFileSelected = (file: File) => {
    setSelectedFile(file);
    setValidationErrors([]);
    setStep('upload');
  };

  const handleImport = () => {
    if (!selectedFile) return;
    setStep('validating');
    uploadCsv(selectedFile);
  };

  const handleClose = () => {
    setSelectedFile(null);
    setValidationErrors([]);
    setStep('upload');
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Bulk Student Import"
      description="Import multiple students at once from a CSV template"
      maxWidth="xl"
    >
      <div className="space-y-5">
        {/* Template Download Banner & Action */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-slate-900 border border-slate-700/80 rounded-xl">
          <div className="space-y-0.5">
            <h5 className="text-xs font-bold text-white flex items-center gap-1.5">
              <span>Official SchoolBridge CSV Template</span>
            </h5>
            <p className="text-[11px] text-slate-400">
              Includes pre-configured columns for Admission No., Ugandan phone validation, and class mapping.
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleDownloadTemplate}
            isLoading={isDownloadingTemplate}
            leftIcon={<Download className="w-4 h-4 text-emerald-400" />}
            className="shrink-0"
          >
            Download Template CSV
          </Button>
        </div>

        {step === 'upload' && (
          <div className="space-y-5">
            <FileDropzone
              onFileSelected={handleFileSelected}
              accept=".csv"
              maxSizeMb={5}
              label="Drag your student CSV here or click to browse"
            />

            {selectedFile && (
              <div className="flex items-center justify-between p-3 bg-slate-900 border border-slate-700 rounded-xl">
                <div className="text-xs text-slate-300">
                  Selected: <span className="text-emerald-400 font-semibold">{selectedFile.name}</span>
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="secondary" size="sm" onClick={handleClose}>Cancel</Button>
                  <Button type="button" variant="primary" size="sm" onClick={handleImport} isLoading={isPending} leftIcon={<Upload className="w-4 h-4" />}>
                    Validate & Import
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {step === 'validating' && (
          <div className="text-center py-8">
            <div className="w-10 h-10 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-sm text-slate-300">Validating and formatting phone numbers...</p>
          </div>
        )}

        {step === 'errors' && validationErrors.length > 0 && (
          <div className="space-y-4">
            <AlertBanner
              type="warning"
              title={`${validationErrors.length} validation issue(s) detected`}
              message="Review the errors below. Phone numbers have been auto-formatted where possible."
            />
            <div className="max-h-64 overflow-y-auto space-y-2">
              {validationErrors.map((err, idx) => (
                <div key={idx} className="flex items-start gap-3 p-3 bg-slate-900 border border-rose-500/20 rounded-xl text-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-slate-200">
                      <span className="font-semibold text-amber-400">Row {err.row}</span> — {err.field}
                    </p>
                    <p className="text-slate-400 mt-0.5">Value: <span className="text-rose-400">{err.value}</span></p>
                    <p className="text-slate-400">{err.error}</p>
                    {err.fixed && (
                      <p className="text-emerald-400 mt-1">✓ Auto-fixed to: {err.fixed}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-3">
              <Button variant="secondary" size="sm" onClick={handleClose}>Cancel</Button>
              <Button variant="primary" size="sm" onClick={handleImport} isLoading={isPending}>
                Retry Import
              </Button>
            </div>
          </div>
        )}

        {step === 'success' && (
          <div className="text-center py-8">
            <CheckCircle2 className="w-14 h-14 text-emerald-400 mx-auto mb-3" />
            <h4 className="text-lg font-bold text-white">Import Successful!</h4>
            <p className="text-sm text-slate-400 mt-1">Students have been enrolled and Student IDs generated.</p>
            <div className="mt-6">
              <Button variant="primary" onClick={handleClose}>Close</Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};

