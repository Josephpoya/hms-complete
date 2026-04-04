/**
 * AppointmentCalendarStrip
 * =========================
 * Horizontal day-picker strip + today's appointment timeline.
 * Used at the top of the appointments page for quick navigation.
 *
 * Features:
 *  - 7-day sliding window centred on today
 *  - Appointment count dots per day
 *  - Click a day to filter the list below
 *  - Mini timeline showing booked slots on the selected day
 */
import React, { useState } from 'react';
import { clsx } from 'clsx';
import { format, addDays, startOfDay, isSameDay, isToday } from 'date-fns';
import { AppointmentCalendar } from '../../types';

interface Props {
  appointments: AppointmentCalendar[];
  onDaySelect:  (date: Date | null) => void;
  selectedDay:  Date | null;
}

const STATUS_DOT: Record<string, string> = {
  booked:      'bg-blue-500',
  checked_in:  'bg-teal-500',
  in_progress: 'bg-amber-500',
  completed:   'bg-green-500',
  cancelled:   'bg-slate-300',
  no_show:     'bg-slate-400',
};

export function AppointmentCalendarStrip({ appointments, onDaySelect, selectedDay }: Props) {
  const today = startOfDay(new Date());
  const days  = Array.from({ length: 7 }, (_, i) => addDays(today, i - 2));

  function countFor(day: Date) {
    return appointments.filter(a =>
      isSameDay(new Date(a.scheduled_at), day) &&
      a.status !== 'cancelled' && a.status !== 'no_show',
    );
  }

  const selectedAppts = selectedDay
    ? appointments
        .filter(a => isSameDay(new Date(a.scheduled_at), selectedDay))
        .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
    : [];

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Day strip */}
      <div className="flex border-b border-slate-100">
        {days.map(day => {
          const dayAppts  = countFor(day);
          const isSelected = selectedDay ? isSameDay(day, selectedDay) : false;
          const isT        = isToday(day);

          return (
            <button
              key={day.toISOString()}
              onClick={() => onDaySelect(isSelected ? null : day)}
              className={clsx(
                'flex-1 flex flex-col items-center py-3 px-1 transition-colors',
                isSelected
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-slate-50 text-slate-700',
              )}
            >
              <span className={clsx(
                'text-xs font-medium uppercase tracking-wide',
                isSelected ? 'text-blue-200' : 'text-slate-400',
              )}>
                {format(day, 'EEE')}
              </span>
              <span className={clsx(
                'text-lg font-bold leading-tight mt-0.5',
                isT && !isSelected && 'text-blue-600',
              )}>
                {format(day, 'd')}
              </span>
              {/* Appointment dots */}
              <div className="flex gap-0.5 mt-1 h-2 items-center">
                {dayAppts.slice(0, 4).map((a, i) => (
                  <span key={i} className={clsx(
                    'w-1.5 h-1.5 rounded-full',
                    isSelected ? 'bg-blue-300' : (STATUS_DOT[a.status] ?? 'bg-slate-300'),
                  )} />
                ))}
                {dayAppts.length > 4 && (
                  <span className={clsx('text-[9px] font-bold', isSelected ? 'text-blue-200' : 'text-slate-400')}>
                    +{dayAppts.length - 4}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Mini timeline for selected day */}
      {selectedDay && selectedAppts.length > 0 && (
        <div className="px-4 py-3 overflow-x-auto">
          <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">
            {format(selectedDay, 'EEEE d MMM')} — {selectedAppts.length} appointment{selectedAppts.length !== 1 ? 's' : ''}
          </p>
          <div className="flex gap-2">
            {selectedAppts.map(a => (
              <div key={a.id}
                className={clsx(
                  'flex-shrink-0 px-2.5 py-1.5 rounded-lg border text-xs',
                  a.status === 'completed' ? 'bg-green-50 border-green-200 text-green-800' :
                  a.status === 'cancelled' ? 'bg-slate-50 border-slate-200 text-slate-500' :
                  a.status === 'in_progress' ? 'bg-amber-50 border-amber-300 text-amber-800' :
                  'bg-white border-slate-200 text-slate-700',
                )}
                style={{ borderLeftWidth: 3, borderLeftColor: a.color_code }}
              >
                <p className="font-bold font-mono">{format(new Date(a.scheduled_at), 'HH:mm')}</p>
                <p className="font-medium truncate max-w-28">{a.patient_name}</p>
                <p className="text-slate-400 truncate max-w-28">{a.doctor_name}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedDay && selectedAppts.length === 0 && (
        <div className="px-4 py-3 text-sm text-slate-400 text-center">
          No appointments on {format(selectedDay, 'EEEE d MMM')}.
        </div>
      )}
    </div>
  );
}
