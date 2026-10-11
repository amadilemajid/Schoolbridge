import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, X } from 'lucide-react';
import { clsx } from 'clsx';

interface FileDropzoneProps {
  onFileSelected: (file: File) => void;
  accept?: string;
  maxSizeMb?: number;
  label?: string;
}

export const FileDropzone: React.FC<FileDropzoneProps> = ({
  onFileSelected,
  accept = '.csv',
  maxSizeMb = 5,
  label = 'Drag and drop your CSV file here, or browse',
}) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = (file: File) => {
    setError(null);
    if (file.size > maxSizeMb * 1024 * 1024) {
      setError(`File size exceeds maximum limit of ${maxSizeMb}MB.`);
      return;
    }

    setSelectedFile(file);
    onFileSelected(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="w-full space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={clsx(
          'border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-3',
          isDragOver
            ? 'border-emerald-500 bg-emerald-500/10'
            : 'border-slate-700 bg-slate-800/50 hover:border-slate-600 hover:bg-slate-800'
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              handleFile(e.target.files[0]);
            }
          }}
        />

        {selectedFile ? (
          <div className="flex items-center gap-3 bg-slate-800 p-3 rounded-xl border border-slate-700 w-full max-w-sm justify-between">
            <div className="flex items-center gap-2.5 truncate">
              <FileText className="w-5 h-5 text-emerald-400 shrink-0" />
              <div className="text-left truncate">
                <p className="text-xs font-semibold text-white truncate">{selectedFile.name}</p>
                <p className="text-[10px] text-slate-400">{(selectedFile.size / 1024).toFixed(1)} KB</p>
              </div>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFile(null);
              }}
              className="p-1 text-slate-400 hover:text-rose-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <>
            <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-emerald-400">
              <UploadCloud className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-200">{label}</p>
              <p className="text-xs text-slate-400 mt-0.5">Supports {accept} up to {maxSizeMb}MB</p>
            </div>
          </>
        )}
      </div>

      {error && <p className="text-xs text-rose-400 text-center">{error}</p>}
    </div>
  );
};
