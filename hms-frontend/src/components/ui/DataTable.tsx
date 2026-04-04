/**
 * DataTable — a production-grade sortable, filterable table wrapper.
 *
 * Features:
 *  - Column-level sort (asc/desc toggle)
 *  - Sticky header
 *  - Loading skeleton rows
 *  - Empty state slot
 *  - Row click handler
 *  - Responsive overflow scroll
 */
import React, { useState } from 'react';
import { clsx } from 'clsx';
import { ChevronsUpDown, ChevronUp, ChevronDown } from 'lucide-react';
import { Spinner } from './index';

export interface Column<T> {
  key:       string;
  header:    string;
  sortable?: boolean;
  width?:    string;
  align?:    'left' | 'right' | 'center';
  render:    (row: T, idx: number) => React.ReactNode;
}

interface DataTableProps<T> {
  columns:    Column<T>[];
  data:       T[];
  loading?:   boolean;
  onRowClick?: (row: T) => void;
  onSort?:    (key: string, dir: 'asc' | 'desc') => void;
  rowKey:     (row: T) => string;
  emptyNode?: React.ReactNode;
  stickyHeader?: boolean;
}

export function DataTable<T>({
  columns, data, loading, onRowClick, onSort,
  rowKey, emptyNode, stickyHeader = true,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  function handleSort(col: Column<T>) {
    if (!col.sortable) return;
    const newDir = sortKey === col.key && sortDir === 'asc' ? 'desc' : 'asc';
    setSortKey(col.key);
    setSortDir(newDir);
    onSort?.(col.key, newDir);
  }

  const ALIGN = { left: 'text-left', right: 'text-right', center: 'text-center' };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead>
          <tr className={clsx(stickyHeader && 'sticky top-0 z-10')}>
            {columns.map(col => (
              <th
                key={col.key}
                style={{ width: col.width }}
                onClick={() => handleSort(col)}
                className={clsx(
                  'px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide',
                  'bg-slate-50 border-b border-slate-200 select-none',
                  col.sortable && 'cursor-pointer hover:text-slate-700 hover:bg-slate-100',
                  ALIGN[col.align ?? 'left'],
                )}
              >
                <span className="flex items-center gap-1">
                  {col.header}
                  {col.sortable && (
                    <span className="text-slate-300">
                      {sortKey !== col.key
                        ? <ChevronsUpDown size={13} />
                        : sortDir === 'asc'
                          ? <ChevronUp   size={13} className="text-blue-500" />
                          : <ChevronDown size={13} className="text-blue-500" />
                      }
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {loading ? (
            // Skeleton rows
            Array.from({ length: 6 }).map((_, i) => (
              <tr key={i}>
                {columns.map(col => (
                  <td key={col.key} className="px-4 py-3.5 border-b border-slate-100">
                    <div className={clsx(
                      'h-3.5 bg-slate-100 rounded animate-pulse',
                      i % 3 === 0 ? 'w-3/4' : i % 3 === 1 ? 'w-1/2' : 'w-2/3',
                    )} />
                  </td>
                ))}
              </tr>
            ))
          ) : !data.length ? (
            <tr>
              <td colSpan={columns.length} className="p-0">
                {emptyNode ?? (
                  <div className="flex items-center justify-center py-14 text-slate-400 text-sm">
                    No records found.
                  </div>
                )}
              </td>
            </tr>
          ) : (
            data.map((row, idx) => (
              <tr
                key={rowKey(row)}
                onClick={() => onRowClick?.(row)}
                className={clsx(
                  'border-b border-slate-100',
                  onRowClick && 'cursor-pointer hover:bg-slate-50',
                  idx % 2 === 0 ? '' : 'bg-slate-50/30',
                )}
              >
                {columns.map(col => (
                  <td
                    key={col.key}
                    className={clsx('px-4 py-3.5 text-slate-700', ALIGN[col.align ?? 'left'])}
                  >
                    {col.render(row, idx)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
