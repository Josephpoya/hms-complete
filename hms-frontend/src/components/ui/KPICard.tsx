/**
 * KPICard — dashboard metric tile with optional sparkline bar,
 * trend indicator, and click-through navigation.
 */
import React from 'react';
import { clsx } from 'clsx';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface KPICardProps {
  label:       string;
  value:       string | number;
  subvalue?:   string;
  icon?:       React.ReactNode;
  trend?:      { value: string; direction: 'up' | 'down' | 'flat'; positive?: boolean };
  colorScheme?: 'blue' | 'teal' | 'amber' | 'red' | 'green' | 'purple';
  onClick?:    () => void;
  loading?:    boolean;
  alert?:      boolean;          // flashes amber border when true
}

const SCHEME = {
  blue:   { icon: 'bg-blue-100 text-blue-600',   text: 'text-blue-700',   ring: 'ring-blue-200'   },
  teal:   { icon: 'bg-teal-100 text-teal-600',   text: 'text-teal-700',   ring: 'ring-teal-200'   },
  amber:  { icon: 'bg-amber-100 text-amber-600', text: 'text-amber-700',  ring: 'ring-amber-200'  },
  red:    { icon: 'bg-red-100 text-red-600',     text: 'text-red-700',    ring: 'ring-red-200'    },
  green:  { icon: 'bg-green-100 text-green-600', text: 'text-green-700',  ring: 'ring-green-200'  },
  purple: { icon: 'bg-purple-100 text-purple-600',text:'text-purple-700', ring: 'ring-purple-200' },
};

export function KPICard({
  label, value, subvalue, icon, trend,
  colorScheme = 'blue', onClick, loading, alert,
}: KPICardProps) {
  const s = SCHEME[colorScheme];

  return (
    <div
      onClick={onClick}
      className={clsx(
        'bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex items-start gap-4',
        'transition-all duration-150',
        onClick && 'cursor-pointer hover:shadow-md hover:-translate-y-0.5',
        alert && 'ring-2 ring-amber-300 border-amber-300',
      )}
    >
      {icon && (
        <div className={clsx('flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center', s.icon)}>
          {icon}
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide leading-none mb-1.5">
          {label}
        </p>

        {loading ? (
          <div className="h-7 w-16 bg-slate-100 rounded animate-pulse" />
        ) : (
          <p className="text-2xl font-bold text-slate-900 leading-tight">
            {value}
          </p>
        )}

        {subvalue && !loading && (
          <p className="text-xs text-slate-500 mt-0.5 truncate">{subvalue}</p>
        )}

        {trend && !loading && (
          <div className={clsx('flex items-center gap-1 mt-1.5 text-xs font-medium',
            trend.direction === 'flat'
              ? 'text-slate-500'
              : (trend.positive ?? trend.direction === 'up')
                ? 'text-green-600' : 'text-red-500',
          )}>
            {trend.direction === 'up'   && <TrendingUp  size={12} />}
            {trend.direction === 'down' && <TrendingDown size={12} />}
            {trend.direction === 'flat' && <Minus        size={12} />}
            <span>{trend.value}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Mini progress bar for capacity indicators ────────────────────────────────
interface CapacityBarProps {
  label:   string;
  current: number;
  max:     number;
  color?:  'blue' | 'amber' | 'red' | 'green';
}

export function CapacityBar({ label, current, max, color = 'blue' }: CapacityBarProps) {
  const pct  = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  const auto = pct >= 90 ? 'red' : pct >= 70 ? 'amber' : color;

  const FILL = { blue: 'bg-blue-500', amber: 'bg-amber-400', red: 'bg-red-500', green: 'bg-green-500' };

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-600 font-medium">{label}</span>
        <span className="text-slate-500">{current}/{max}</span>
      </div>
      <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all duration-300', FILL[auto])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
