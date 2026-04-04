/**
 * PatientAutocomplete
 * ====================
 * Async search-as-you-type patient selector used in booking and billing forms.
 *
 * - Debounced search (350ms)
 * - Displays MRN + phone in dropdown
 * - Keyboard navigation (↑↓ Enter Escape)
 * - Cleared when user edits the text after selection
 * - Shows a "selected" chip when a patient is confirmed
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { clsx } from 'clsx';
import { Search, X, User, ChevronRight } from 'lucide-react';
import { patientService } from '../../services/patientService';
import { PatientMinimal } from '../../types';

interface Props {
  value:       string;            // selected patient id
  onChange:    (id: string, patient?: PatientMinimal) => void;
  label?:      string;
  error?:      string;
  placeholder?: string;
  disabled?:   boolean;
}

export function PatientAutocomplete({
  value, onChange, label = 'Patient', error,
  placeholder = 'Type name or MRN to search…', disabled,
}: Props) {
  const [query,    setQuery]    = useState('');
  const [options,  setOptions]  = useState<PatientMinimal[]>([]);
  const [selected, setSelected] = useState<PatientMinimal | null>(null);
  const [open,     setOpen]     = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [cursor,   setCursor]   = useState(-1);
  const inputRef  = useRef<HTMLInputElement>(null);
  const listRef   = useRef<HTMLUListElement>(null);

  // Resolve pre-selected patient by id on mount
  useEffect(() => {
    if (!value || selected?.id === value) return;
    // No patient detail endpoint for minimal data — clear if id changes externally
    setSelected(null);
  }, [value]);

  // Debounced search
  useEffect(() => {
    if (query.length < 2) { setOptions([]); return; }
    setLoading(true);
    const t = setTimeout(() => {
      patientService.search(query)
        .then(results => { setOptions(results); setOpen(true); setCursor(-1); })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  function select(p: PatientMinimal) {
    setSelected(p);
    setQuery('');
    setOptions([]);
    setOpen(false);
    onChange(p.id, p);
  }

  function clear() {
    setSelected(null);
    setQuery('');
    setOptions([]);
    onChange('');
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open || !options.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, options.length - 1)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)); }
    if (e.key === 'Enter' && cursor >= 0) { e.preventDefault(); select(options[cursor]); }
    if (e.key === 'Escape') { setOpen(false); setCursor(-1); }
  }

  return (
    <div className="relative w-full">
      {label && (
        <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      )}

      {selected ? (
        // Selected chip
        <div className={clsx(
          'flex items-center gap-2 px-3 py-2 rounded-lg border bg-blue-50 border-blue-200',
          disabled && 'opacity-60',
        )}>
          <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
            <User size={12} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-blue-900 truncate">{selected.full_name}</p>
            <p className="text-xs text-blue-600 font-mono">{selected.mrn} · {selected.phone}</p>
          </div>
          {!disabled && (
            <button type="button" onClick={clear}
              className="flex-shrink-0 p-0.5 rounded text-blue-400 hover:text-blue-700 hover:bg-blue-100 transition-colors">
              <X size={14} />
            </button>
          )}
        </div>
      ) : (
        // Search input
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            disabled={disabled}
            onChange={e => { setQuery(e.target.value); setOpen(true); }}
            onKeyDown={handleKeyDown}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onFocus={() => query.length >= 2 && setOpen(true)}
            placeholder={placeholder}
            autoComplete="off"
            className={clsx(
              'w-full pl-9 pr-3 py-2 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
              error
                ? 'border-red-400 focus:ring-red-200'
                : 'border-slate-300 focus:border-blue-500 focus:ring-blue-200',
              disabled && 'opacity-60 cursor-not-allowed bg-slate-50',
            )}
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-3.5 h-3.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
      )}

      {/* Dropdown */}
      {open && options.length > 0 && (
        <ul ref={listRef}
          className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden max-h-56 overflow-y-auto">
          {options.map((p, i) => (
            <li key={p.id}>
              <button
                type="button"
                onMouseDown={() => select(p)}
                className={clsx(
                  'w-full flex items-center justify-between px-3 py-2.5 text-left',
                  'hover:bg-blue-50 transition-colors border-b border-slate-100 last:border-b-0',
                  cursor === i && 'bg-blue-50',
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">{p.full_name}</p>
                  <p className="text-xs text-slate-500 font-mono">{p.mrn} · {p.phone}</p>
                </div>
                <ChevronRight size={14} className="text-slate-300 flex-shrink-0 ml-2" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && query.length >= 2 && !loading && options.length === 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg p-4 text-center text-sm text-slate-400">
          No patients found for "{query}"
        </div>
      )}

      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
