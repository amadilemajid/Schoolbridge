import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { clsx } from 'clsx';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  width?: 'md' | 'lg' | 'xl';
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  width = 'lg',
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const widthStyles = {
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Drawer Container */}
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div
          className={clsx(
            'w-screen bg-slate-900 border-l border-slate-700/80 shadow-2xl flex flex-col',
            widthStyles[width]
          )}
        >
          {/* Header */}
          {(title || description) && (
            <div className="px-6 py-5 border-b border-slate-800 flex items-start justify-between gap-4">
              <div>
                {title && <h3 className="text-lg font-bold text-white tracking-tight">{title}</h3>}
                {description && <p className="text-xs text-slate-400 mt-0.5">{description}</p>}
              </div>
              <button
                onClick={onClose}
                className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-800 transition-colors"
                aria-label="Close drawer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          )}

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto">{children}</div>
        </div>
      </div>
    </div>
  );
};
