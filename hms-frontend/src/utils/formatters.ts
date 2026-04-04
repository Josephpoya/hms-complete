/**
 * utils/formatters.ts
 * ====================
 * Pure formatting helpers used across multiple components.
 */

import { format, parseISO, formatDistanceToNow, isValid } from 'date-fns';

export const fmt = {
  /** "15 Jan 2024" */
  date: (iso: string | undefined | null): string => {
    if (!iso) return '—';
    try { return format(parseISO(iso), 'dd MMM yyyy'); }
    catch { return iso; }
  },

  /** "15 Jan 2024, 14:30" */
  datetime: (iso: string | undefined | null): string => {
    if (!iso) return '—';
    try { return format(parseISO(iso), 'dd MMM yyyy, HH:mm'); }
    catch { return iso; }
  },

  /** "14:30" */
  time: (iso: string | undefined | null): string => {
    if (!iso) return '—';
    try { return format(parseISO(iso), 'HH:mm'); }
    catch { return iso; }
  },

  /** "3 hours ago" */
  relative: (iso: string | undefined | null): string => {
    if (!iso) return '—';
    try { return formatDistanceToNow(parseISO(iso), { addSuffix: true }); }
    catch { return iso; }
  },

  /** "UGX 45,000" */
  currency: (amount: string | number | undefined | null, currency = 'UGX'): string => {
    if (amount == null || amount === '') return '—';
    const n = typeof amount === 'string' ? parseFloat(amount) : amount;
    if (isNaN(n)) return '—';
    return `${currency} ${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  },

  /** "John D." — safe display for logs */
  safeName: (fullName: string | undefined | null): string => {
    if (!fullName) return 'Unknown';
    const parts = fullName.trim().split(' ');
    if (parts.length === 1) return parts[0];
    return `${parts[0]} ${parts[parts.length - 1].charAt(0)}.`;
  },

  /** "30 min" / "1h 30min" */
  duration: (minutes: number): string => {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (h && m) return `${h}h ${m}min`;
    if (h)      return `${h}h`;
    return `${m}min`;
  },
};
