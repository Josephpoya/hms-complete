/**
 * components/ui/index.tsx
 * ========================
 * Shared UI primitives used across all pages.
 */

import React from 'react';
import { clsx } from 'clsx';
import { AlertTriangle, CheckCircle, Info, XCircle, Loader2 } from 'lucide-react';

// ─── Badge ────────────────────────────────────────────────────────────────────
type BadgeVariant = 'gray' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'teal';

const BADGE_STYLES: Record<BadgeVariant, string> = {
  gray:   'bg-slate-100 text-slate-700',
  blue:   'bg-blue-100 text-blue-800',
  green:  'bg-green-100 text-green-800',
  amber:  'bg-amber-100 text-amber-800',
  red:    'bg-red-100 text-red-800',
  purple: 'bg-purple-100 text-purple-800',
  teal:   'bg-teal-100 text-teal-800',
};

export function Badge({ children, variant = 'gray', className }: {
  children: React.ReactNode; variant?: BadgeVariant; className?: string;
}) {
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded text-xs font-medium', BADGE_STYLES[variant], className)}>
      {children}
    </span>
  );
}

// ─── Appointment status badge ─────────────────────────────────────────────────
export function StatusBadge({ status }: { status: string }) {
  const MAP: Record<string, BadgeVariant> = {
    booked: 'blue', checked_in: 'teal', in_progress: 'amber',
    completed: 'green', cancelled: 'red', no_show: 'gray',
    draft: 'gray', issued: 'blue', partially_paid: 'amber',
    paid: 'green', voided: 'gray', overdue: 'red',
    pending: 'amber', dispensed: 'green', expired: 'gray',
  };
  return <Badge variant={MAP[status] ?? 'gray'}>{status.replace('_', ' ')}</Badge>;
}

// ─── Button ───────────────────────────────────────────────────────────────────
type BtnVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type BtnSize    = 'sm' | 'md' | 'lg';

const BTN_BASE = 'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none focus:outline-none focus:ring-2 focus:ring-offset-1';
const BTN_VARIANTS: Record<BtnVariant, string> = {
  primary:   'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500',
  secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 focus:ring-slate-400',
  danger:    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  ghost:     'text-slate-600 hover:bg-slate-100 focus:ring-slate-400',
};
const BTN_SIZES: Record<BtnSize, string> = {
  sm: 'text-xs px-2.5 py-1.5', md: 'text-sm px-4 py-2', lg: 'text-base px-5 py-2.5',
};

export function Button({ children, variant = 'primary', size = 'md', isLoading, className, ...props }: {
  children: React.ReactNode; variant?: BtnVariant; size?: BtnSize;
  isLoading?: boolean; className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={clsx(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      disabled={isLoading || props.disabled}
      {...props}
    >
      {isLoading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

// ─── Input ────────────────────────────────────────────────────────────────────
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string }>(
  ({ label, error, className, id, ...props }, ref) => (
    <div className="w-full">
      {label && <label htmlFor={id} className="block text-sm font-medium text-slate-700 mb-1">{label}</label>}
      <input
        ref={ref} id={id}
        className={clsx(
          'w-full rounded-lg border px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 transition-colors',
          error
            ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
            : 'border-slate-300 focus:border-blue-500 focus:ring-blue-200',
          className,
        )}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
);
Input.displayName = 'Input';

// ─── Select ───────────────────────────────────────────────────────────────────
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string; error?: string }>(
  ({ label, error, className, id, children, ...props }, ref) => (
    <div className="w-full">
      {label && <label htmlFor={id} className="block text-sm font-medium text-slate-700 mb-1">{label}</label>}
      <select
        ref={ref} id={id}
        className={clsx(
          'w-full rounded-lg border px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 transition-colors bg-white',
          error ? 'border-red-400 focus:ring-red-200' : 'border-slate-300 focus:border-blue-500 focus:ring-blue-200',
          className,
        )}
        {...props}
      >
        {children}
      </select>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
);
Select.displayName = 'Select';

// ─── Card ─────────────────────────────────────────────────────────────────────
export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('bg-white rounded-xl border border-slate-200 shadow-sm', className)}>{children}</div>;
}
export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('px-5 py-4 border-b border-slate-100', className)}>{children}</div>;
}
export function CardContent({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('px-5 py-4', className)}>{children}</div>;
}

// ─── Alert ────────────────────────────────────────────────────────────────────
type AlertVariant = 'info' | 'success' | 'warning' | 'error';
const ALERT_STYLES: Record<AlertVariant, { wrapper: string; icon: React.ReactNode }> = {
  info:    { wrapper: 'bg-blue-50 border-blue-200 text-blue-800',    icon: <Info size={16} className="text-blue-500 flex-shrink-0" /> },
  success: { wrapper: 'bg-green-50 border-green-200 text-green-800', icon: <CheckCircle size={16} className="text-green-500 flex-shrink-0" /> },
  warning: { wrapper: 'bg-amber-50 border-amber-200 text-amber-800', icon: <AlertTriangle size={16} className="text-amber-500 flex-shrink-0" /> },
  error:   { wrapper: 'bg-red-50 border-red-200 text-red-800',       icon: <XCircle size={16} className="text-red-500 flex-shrink-0" /> },
};

export function Alert({ variant = 'info', title, children }: {
  variant?: AlertVariant; title?: string; children: React.ReactNode;
}) {
  const s = ALERT_STYLES[variant];
  return (
    <div className={clsx('flex items-start gap-2.5 p-3.5 rounded-lg border text-sm', s.wrapper)}>
      {s.icon}
      <div>{title && <p className="font-medium mb-0.5">{title}</p>}{children}</div>
    </div>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────
export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const s = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' }[size];
  return <div className={clsx(s, 'border-2 border-blue-600 border-t-transparent rounded-full animate-spin')} />;
}

// ─── Empty state ──────────────────────────────────────────────────────────────
export function EmptyState({ icon, title, description, action }: {
  icon?: React.ReactNode; title: string; description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && <div className="mb-4 text-slate-300">{icon}</div>}
      <h3 className="text-base font-medium text-slate-700 mb-1">{title}</h3>
      {description && <p className="text-sm text-slate-500 max-w-sm mb-4">{description}</p>}
      {action}
    </div>
  );
}

// ─── Stat card ────────────────────────────────────────────────────────────────
export function StatCard({ label, value, icon, trend, color = 'blue' }: {
  label: string; value: string | number; icon?: React.ReactNode;
  trend?: { value: string; up: boolean }; color?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-4">
        {icon && (
          <div className={clsx('p-2.5 rounded-lg', `bg-${color}-100`)}>
            <span className={clsx(`text-${color}-600`)}>{icon}</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
          <p className="text-2xl font-bold text-slate-900 mt-0.5">{value}</p>
          {trend && (
            <p className={clsx('text-xs mt-1', trend.up ? 'text-green-600' : 'text-red-600')}>
              {trend.up ? '↑' : '↓'} {trend.value}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Table ────────────────────────────────────────────────────────────────────
export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={clsx('w-full text-sm text-left', className)}>
        {children}
      </table>
    </div>
  );
}
export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th className={clsx('px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide bg-slate-50 border-b border-slate-200', className)}>
      {children}
    </th>
  );
}
export function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={clsx('px-4 py-3.5 border-b border-slate-100 text-slate-700', className)}>{children}</td>;
}

// ─── Pagination ───────────────────────────────────────────────────────────────
export function Pagination({ page, total, pageSize, onChange }: {
  page: number; total: number; pageSize: number; onChange: (p: number) => void;
}) {
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
      <p className="text-sm text-slate-500">
        Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
      </p>
      <div className="flex items-center gap-1">
        {Array.from({ length: Math.min(pages, 7) }, (_, i) => i + 1).map(p => (
          <button
            key={p}
            onClick={() => onChange(p)}
            className={clsx(
              'w-8 h-8 text-xs rounded-md transition-colors',
              p === page
                ? 'bg-blue-600 text-white font-medium'
                : 'text-slate-600 hover:bg-slate-100',
            )}
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────────
export function Modal({ isOpen, onClose, title, children, size = 'md' }: {
  isOpen: boolean; onClose: () => void; title: string;
  children: React.ReactNode; size?: 'sm' | 'md' | 'lg';
}) {
  if (!isOpen) return null;
  const widths = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl' };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className={clsx('relative bg-white rounded-xl shadow-xl w-full', widths[size])}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100">
            <XCircle size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
