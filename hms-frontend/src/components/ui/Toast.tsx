/**
 * components/ui/Toast.tsx
 * ========================
 * Toast notification system.
 * Mount <ToastContainer /> once in AppLayout.
 * Call toast('message', 'success') from anywhere.
 */

import React from 'react';
import { clsx } from 'clsx';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import { useToastState } from '../../hooks/useApi';

const STYLES = {
  success: { wrapper: 'bg-white border-green-400',  icon: <CheckCircle   size={18} className="text-green-500" />, title: 'text-green-800' },
  error:   { wrapper: 'bg-white border-red-400',    icon: <XCircle       size={18} className="text-red-500"   />, title: 'text-red-800'   },
  warning: { wrapper: 'bg-white border-amber-400',  icon: <AlertTriangle size={18} className="text-amber-500" />, title: 'text-amber-800' },
  info:    { wrapper: 'bg-white border-blue-400',   icon: <Info          size={18} className="text-blue-500"  />, title: 'text-blue-800'  },
};

export function ToastContainer() {
  const toasts = useToastState();
  if (!toasts.length) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full">
      {toasts.map(t => {
        const s = STYLES[t.variant];
        return (
          <div key={t.id}
            className={clsx(
              'flex items-start gap-3 p-3.5 rounded-xl border-l-4 shadow-lg',
              'animate-in slide-in-from-right-5 duration-200',
              s.wrapper,
            )}
          >
            <span className="flex-shrink-0 mt-0.5">{s.icon}</span>
            <p className={clsx('text-sm font-medium flex-1', s.title)}>{t.message}</p>
          </div>
        );
      })}
    </div>
  );
}
