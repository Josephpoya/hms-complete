/**
 * pages/appointments/AppointmentsPage.tsx  (full rewrite)
 * =========================================================
 * - Today view + full list with filters
 * - State-machine status transitions
 * - Booking modal integrated
 * - Priority-colour left border on each card
 */

import React, { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { appointmentService } from '../../services/appointmentService';
import { usePaginatedQuery, useMutation, useDebounce } from '../../hooks/useApi';
import { toast } from '../../hooks/useApi';
import { Appointment, AppointmentStatus } from '../../types';
import {
  Card, CardHeader, CardContent, Table, Th, Td, Pagination,
  Button, StatusBadge, Alert, Spinner, EmptyState, Modal,
} from '../../components/ui';
import { FilterBar }   from '../../components/shared/FilterBar';
import { PageHeader }  from '../../components/shared/PageHeader';
import { ConfirmDialog } from '../../components/shared/ConfirmDialog';
import { AppointmentBookingForm } from '../../components/forms/AppointmentBookingForm';
import { Calendar, Plus, Stethoscope, User, Clock } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { clsx } from 'clsx';

type StatusAction = { next: AppointmentStatus; label: string; color: string };

const ACTIONS: Partial<Record<AppointmentStatus, StatusAction[]>> = {
  booked:      [{ next: 'checked_in',  label: 'Check in',   color: 'teal' },
                { next: 'cancelled',   label: 'Cancel',      color: 'red'  }],
  checked_in:  [{ next: 'in_progress', label: 'Start',       color: 'blue' },
                { next: 'no_show',     label: 'No show',     color: 'gray' }],
  in_progress: [{ next: 'completed',   label: 'Complete',    color: 'green'}],
};

const PRIORITY_BORDER: Record<number, string> = {
  1: 'border-l-4 border-l-red-500',
  2: 'border-l-4 border-l-amber-400',
  3: 'border-l-4 border-l-blue-400',
  4: 'border-l-4 border-l-slate-200',
};

export function AppointmentsPage() {
  const { can } = useAuth();

  const [search,   setSearch]   = useState('');
  const [statusF,  setStatusF]  = useState('');
  const [bookOpen, setBookOpen] = useState(false);

  const [statusModal, setStatusModal] = useState<{
    appt: Appointment; action: StatusAction;
  } | null>(null);
  const [cancelReason, setCancelReason] = useState('');

  const debouncedSearch = useDebounce(search);

  const { data, loading, error, page, setPage, refetch } = usePaginatedQuery(
    (p) => appointmentService.list({
      search:   debouncedSearch || undefined,
      status:   statusF        || undefined,
      page: p,
      ordering: '-scheduled_at',
    }),
    [debouncedSearch, statusF],
  );

  const transition = useMutation(
    ({ id, status, reason }: { id: string; status: AppointmentStatus; reason?: string }) =>
      appointmentService.changeStatus(id, status, reason),
    {
      onSuccess: () => {
        toast('Status updated.', 'success');
        setStatusModal(null);
        setCancelReason('');
        refetch();
      },
    },
  );

  function openAction(appt: Appointment, action: StatusAction) {
    if (action.next === 'cancelled') {
      setCancelReason('');
    }
    setStatusModal({ appt, action });
  }

  async function confirmAction() {
    if (!statusModal) return;
    await transition.mutate({
      id:     statusModal.appt.id,
      status: statusModal.action.next,
      reason: statusModal.action.next === 'cancelled' ? cancelReason : undefined,
    });
  }

  const STATUS_TABS = ['', 'booked', 'checked_in', 'in_progress', 'completed', 'cancelled', 'no_show'];

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Appointments"
        subtitle={data ? `${data.count.toLocaleString()} total` : undefined}
        actions={
          can('appointments:write') ? (
            <Button size="sm" onClick={() => setBookOpen(true)}>
              <Plus size={14} /> Book appointment
            </Button>
          ) : undefined
        }
      />

      {error && <Alert variant="error">{error}</Alert>}
      {transition.error && <Alert variant="error">{transition.error}</Alert>}

      {/* Filter bar */}
      <FilterBar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Search patient name, MRN, doctor…"
      >
        <div className="flex flex-wrap gap-1">
          {STATUS_TABS.map(s => (
            <button key={s}
              onClick={() => { setStatusF(s); setPage(1); }}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize whitespace-nowrap',
                statusF === s
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}>
              {s === '' ? 'All' : s.replace('_', ' ')}
            </button>
          ))}
        </div>
      </FilterBar>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : !data?.results.length ? (
        <EmptyState
          icon={<Calendar size={40} />}
          title="No appointments found"
          description={search ? `No results for "${search}"` : 'No appointments scheduled.'}
          action={can('appointments:write') ? (
            <Button size="sm" onClick={() => setBookOpen(true)}>
              <Plus size={14} /> Book appointment
            </Button>
          ) : undefined}
        />
      ) : (
        <div className="space-y-2">
          {data.results.map(appt => (
            <div key={appt.id}
              className={clsx('bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden', PRIORITY_BORDER[appt.priority])}>
              <div className="flex items-center gap-4 px-5 py-4">
                {/* Time block */}
                <div className="flex-shrink-0 w-16 text-center">
                  <p className="text-lg font-bold text-slate-900 font-mono leading-none">
                    {format(parseISO(appt.scheduled_at), 'HH:mm')}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">{appt.duration_display}</p>
                  <p className="text-xs text-slate-400">{format(parseISO(appt.scheduled_at), 'dd MMM')}</p>
                </div>

                <div className="w-px h-10 bg-slate-200 flex-shrink-0" />

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                      <User size={13} className="text-slate-400" />
                      {appt.patient_name}
                    </span>
                    {appt.patient_mrn && (
                      <span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">
                        {appt.patient_mrn}
                      </span>
                    )}
                    {appt.doctor_name && (
                      <span className="text-xs text-slate-500 flex items-center gap-1">
                        <Stethoscope size={11} /> {appt.doctor_name}
                      </span>
                    )}
                  </div>
                  {appt.chief_complaint && (
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{appt.chief_complaint}</p>
                  )}
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-xs text-slate-400 capitalize">
                      {appt.appointment_type?.replace('_', ' ')}
                    </span>
                    <StatusBadge status={appt.status} />
                  </div>
                </div>

                {/* Actions */}
                {can('appointments:status') && (
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {(ACTIONS[appt.status] ?? []).map(action => (
                      <button
                        key={action.next}
                        onClick={() => openAction(appt, action)}
                        className={clsx(
                          'text-xs px-3 py-1.5 rounded-lg font-medium transition-colors',
                          action.color === 'red'   ? 'bg-red-50 text-red-700 hover:bg-red-100' :
                          action.color === 'green' ? 'bg-green-50 text-green-700 hover:bg-green-100' :
                          action.color === 'teal'  ? 'bg-teal-50 text-teal-700 hover:bg-teal-100' :
                          action.color === 'gray'  ? 'bg-slate-100 text-slate-600 hover:bg-slate-200' :
                          'bg-blue-50 text-blue-700 hover:bg-blue-100',
                        )}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          <Pagination page={page} total={data.count} pageSize={20} onChange={setPage} />
        </div>
      )}

      {/* Booking modal */}
      <Modal isOpen={bookOpen} onClose={() => setBookOpen(false)} title="Book appointment" size="lg">
        <AppointmentBookingForm
          onSuccess={() => { setBookOpen(false); refetch(); }}
          onCancel={() => setBookOpen(false)}
        />
      </Modal>

      {/* Status transition modal */}
      {statusModal && statusModal.action.next === 'cancelled' ? (
        <Modal isOpen onClose={() => setStatusModal(null)} title="Cancel appointment" size="sm">
          <Alert variant="warning">Please provide a reason for cancellation.</Alert>
          <textarea
            value={cancelReason}
            onChange={e => setCancelReason(e.target.value)}
            placeholder="Reason for cancellation…"
            rows={3}
            className="w-full mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none"
          />
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="secondary" onClick={() => setStatusModal(null)}>Back</Button>
            <Button variant="danger" onClick={confirmAction}
              isLoading={transition.loading} disabled={!cancelReason.trim()}>
              Confirm cancellation
            </Button>
          </div>
        </Modal>
      ) : (
        <ConfirmDialog
          isOpen={!!statusModal && statusModal.action.next !== 'cancelled'}
          onClose={() => setStatusModal(null)}
          onConfirm={confirmAction}
          title={`${statusModal?.action.label}: ${statusModal?.appt.patient_name}`}
          message={`Move appointment to "${statusModal?.action.next?.replace('_', ' ')}"?`}
          variant="warning"
          confirmLabel={statusModal?.action.label}
          loading={transition.loading}
        />
      )}
    </div>
  );
}
