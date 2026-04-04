/**
 * A controlled search input with debounce and clear button.
 */
import React, { useState, useEffect } from 'react';
import { Search, X } from 'lucide-react';
import { clsx } from 'clsx';

interface Props {
  value:       string;
  onChange:    (v: string) => void;
  placeholder?: string;
  debounceMs?: number;
  className?:  string;
}

export function SearchInput({ value, onChange, placeholder = 'Search…', debounceMs = 350, className }: Props) {
  const [local, setLocal] = useState(value);

  useEffect(() => setLocal(value), [value]);

  useEffect(() => {
    const t = setTimeout(() => onChange(local), debounceMs);
    return () => clearTimeout(t);
  }, [local, debounceMs, onChange]);

  return (
    <div className={clsx('relative', className)}>
      <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      <input
        type="search"
        value={local}
        onChange={e => setLocal(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-8 py-2 rounded-lg border border-slate-300 text-sm
                   focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-500 transition-colors"
      />
      {local && (
        <button onClick={() => { setLocal(''); onChange(''); }}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
          <X size={14} />
        </button>
      )}
    </div>
  );
}
