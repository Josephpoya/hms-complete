/**
 * InvoiceLineItems
 * =================
 * Live-editable invoice line item list.
 *
 * Displays a running total that updates as the user types.
 * Used inside InvoiceCreateForm and InvoiceDetailPage.
 *
 * Modes:
 *   editable=true  → add/remove/edit rows inline
 *   editable=false → read-only display (issued invoices)
 */
import React, { useCallback } from 'react';
import { clsx } from 'clsx';
import { Plus, Trash2, AlertCircle } from 'lucide-react';

export interface LineItem {
  id?:          string;          // set when persisted
  description:  string;
  item_type:    string;
  unit_price:   string;
  quantity:     number;
  line_total?:  string;          // from API; computed locally when not present
}

const ITEM_TYPES = [
  { value: 'consultation', label: 'Consultation' },
  { value: 'procedure',    label: 'Procedure' },
  { value: 'lab',          label: 'Laboratory' },
  { value: 'pharmacy',     label: 'Pharmacy' },
  { value: 'supply',       label: 'Medical supply' },
  { value: 'radiology',    label: 'Radiology' },
  { value: 'nursing',      label: 'Nursing care' },
  { value: 'other',        label: 'Other' },
];

function lineTotal(item: LineItem): number {
  const price = parseFloat(item.unit_price) || 0;
  return price * item.quantity;
}

interface Props {
  items:     LineItem[];
  onChange?: (items: LineItem[]) => void;
  editable?: boolean;
  currency?: string;
  errors?:   Record<number, Partial<Record<keyof LineItem, string>>>;
}

export function InvoiceLineItems({
  items, onChange, editable = true, currency = 'UGX', errors = {},
}: Props) {
  const subtotal = items.reduce((s, item) => s + lineTotal(item), 0);

  const update = useCallback((idx: number, field: keyof LineItem, value: string | number) => {
    const next = items.map((item, i) =>
      i === idx ? { ...item, [field]: value } : item
    );
    onChange?.(next);
  }, [items, onChange]);

  const addRow = useCallback(() => {
    onChange?.([...items, { description: '', item_type: 'consultation', unit_price: '', quantity: 1 }]);
  }, [items, onChange]);

  const removeRow = useCallback((idx: number) => {
    onChange?.(items.filter((_, i) => i !== idx));
  }, [items, onChange]);

  const INPUT = 'w-full border border-slate-200 rounded-md px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 focus:border-blue-400 bg-white transition-colors';
  const INPUT_ERR = 'border-red-400 focus:ring-red-300 focus:border-red-400';

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="grid gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wide px-1"
        style={{ gridTemplateColumns: '2.5fr 1.4fr 80px 80px 90px 28px' }}>
        <span>Description</span>
        <span>Type</span>
        <span className="text-right">Price</span>
        <span className="text-center">Qty</span>
        <span className="text-right">Total</span>
        <span />
      </div>

      {/* Rows */}
      {items.length === 0 && (
        <div className="py-8 text-center text-sm text-slate-400 border border-dashed border-slate-200 rounded-lg">
          No items yet.{editable && ' Click "Add item" to begin.'}
        </div>
      )}

      {items.map((item, idx) => {
        const total  = lineTotal(item);
        const rowErr = errors[idx] ?? {};

        return (
          <div key={idx}
            className={clsx(
              'grid gap-2 items-start p-2 rounded-lg transition-colors',
              'bg-white border border-slate-100 hover:border-slate-200',
            )}
            style={{ gridTemplateColumns: '2.5fr 1.4fr 80px 80px 90px 28px' }}
          >
            {/* Description */}
            <div>
              {editable ? (
                <>
                  <input
                    className={clsx(INPUT, rowErr.description && INPUT_ERR)}
                    placeholder="Service or item name…"
                    value={item.description}
                    onChange={e => update(idx, 'description', e.target.value)}
                  />
                  {rowErr.description && (
                    <p className="mt-0.5 text-xs text-red-600 flex items-center gap-0.5">
                      <AlertCircle size={10} /> {rowErr.description}
                    </p>
                  )}
                </>
              ) : (
                <span className="text-sm font-medium text-slate-800">{item.description}</span>
              )}
            </div>

            {/* Type */}
            <div>
              {editable ? (
                <select
                  className={clsx(INPUT, 'pr-1')}
                  value={item.item_type}
                  onChange={e => update(idx, 'item_type', e.target.value)}
                >
                  {ITEM_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              ) : (
                <span className="text-xs text-slate-500 capitalize">
                  {ITEM_TYPES.find(t => t.value === item.item_type)?.label ?? item.item_type}
                </span>
              )}
            </div>

            {/* Unit price */}
            <div>
              {editable ? (
                <input
                  type="number" min="0" step="1"
                  className={clsx(INPUT, 'text-right', rowErr.unit_price && INPUT_ERR)}
                  placeholder="0"
                  value={item.unit_price}
                  onChange={e => update(idx, 'unit_price', e.target.value)}
                />
              ) : (
                <span className="text-sm text-right block">
                  {parseFloat(item.unit_price || '0').toLocaleString()}
                </span>
              )}
            </div>

            {/* Quantity */}
            <div>
              {editable ? (
                <input
                  type="number" min="1" step="1"
                  className={clsx(INPUT, 'text-center')}
                  value={item.quantity}
                  onChange={e => update(idx, 'quantity', Math.max(1, parseInt(e.target.value) || 1))}
                />
              ) : (
                <span className="text-sm text-center block">{item.quantity}</span>
              )}
            </div>

            {/* Line total */}
            <div className="flex items-center justify-end">
              <span className="text-sm font-semibold text-slate-800">
                {total > 0 ? total.toLocaleString() : '—'}
              </span>
            </div>

            {/* Remove */}
            <div className="flex items-center justify-center">
              {editable && (
                <button type="button" onClick={() => removeRow(idx)}
                  className="p-1 rounded text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors">
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          </div>
        );
      })}

      {/* Add row */}
      {editable && (
        <button
          type="button"
          onClick={addRow}
          className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg border border-dashed border-slate-300 text-sm text-slate-500 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
        >
          <Plus size={14} /> Add item
        </button>
      )}

      {/* Subtotal */}
      <div className="flex justify-end pt-3 border-t border-slate-200">
        <div className="text-right space-y-1 min-w-40">
          <div className="flex justify-between gap-8 text-sm text-slate-600">
            <span>Subtotal</span>
            <span className="font-medium">{currency} {subtotal.toLocaleString()}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
