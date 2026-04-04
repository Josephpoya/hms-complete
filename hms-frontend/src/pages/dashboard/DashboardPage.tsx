/**
 * DashboardPage — role-aware KPI dashboard.
 *
 * Sections:
 *  1. Greeting + date
 *  2. KPI cards (filtered by role/permission)
 *  3. Today's schedule (live appointment list)
 *  4. Doctor workload panel (admin/receptionist)
 *  5. Stock alerts (pharmacy access)
 *  6. Quick actions
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { useQuery } from '../../hooks/useApi';
import { appointmentService } from '../../services/appointmentService';
import { pharmacyService }    from '../../services/pharmacyService';
import api                    from '../../services/api';
import { KPICard, CapacityBar } from '../../components/ui/KPICard';
import { Modal, StatusBadge, Spinner, EmptyState, Button } from '../../components/ui';
import { AppointmentBookingForm } from '../../components/forms/AppointmentBookingForm';
import {
  Users, Calendar, FileText, Pill, Stethoscope,
  AlertTriangle, Plus, Clock, TrendingUp, Activity,
  CheckCircle2, XCircle,
} from 'lucide-react';
import { fmt } from '../../utils/formatters';
import { format, parseISO } from 'date-fns';
import { clsx } from 'clsx';

const PRIORITY_LEFT: Record<number, string> = {
  1: 'border-l-[3px] border-l-red-500',
  2: 'border-l-[3px] border-l-amber-400',
  3: 'border-l-[3px] border-l-slate-200',
  4: 'border-l-[3px] border-l-slate-200',
};

export function DashboardPage() {
  const { user, payload, can } = useAuth();
  const navigate   = useNavigate();
  const [bookOpen, setBookOpen] = useState(false);

  // Data fetching
  const { data: todayAppts, loading: loadAppts } = useQuery(
    () => appointmentService.today(),
    [],
  );
  const { data: lowStock, loading: loadStock } = useQuery(
    () => pharmacyService.drugs.lowStock(),
    [],
  );
  const { data: workload, loading: loadWork } = useQuery(
    () => api.get('/doctors/workload/').then(r => r.data),
    [],
  );

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  // Derived stats
  const appts: any[] = Array.isArray(todayAppts) ? todayAppts : ((todayAppts as any)?.results ?? []);
  const totalToday   = appts.length;
  const bookedCount  = appts.filter((a: any) => a.status === 'booked').length;
  const activeCount  = appts.filter((a: any) => a.status === 'in_progress').length;
  const doneCount    = appts.filter((a: any) => a.status === 'completed').length;
  const stockAlerts  = lowStock?.results?.length ?? 0;
  const availDoctors = workload?.filter?.((d: any) => d.is_available && !d.is_fully_booked)?.length ?? 0;

  return (
    <div className="max-w-7xl mx-auto space-y-6">

      {/* ── Greeting ─────────────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {greeting}, {user?.email?.split('@')[0]}
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {format(new Date(), "EEEE, d MMMM yyyy")}
            {payload && <span className="ml-2">· {user?.role_display}</span>}
          </p>
        </div>
        {can('appointments:write') && (
          <Button size="sm" onClick={() => setBookOpen(true)}>
            <Plus size={14} /> Quick book
          </Button>
        )}
      </div>

      {/* ── KPI row ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <KPICard
          label="Today's appointments"
          value={loadAppts ? '—' : totalToday}
          subvalue={`${bookedCount} booked · ${activeCount} active`}
          icon={<Calendar size={20} />}
          colorScheme="blue"
          onClick={() => navigate('/appointments')}
          loading={loadAppts}
        />

        <KPICard
          label="Completed today"
          value={loadAppts ? '—' : doneCount}
          subvalue={totalToday > 0 ? `${Math.round((doneCount / totalToday) * 100)}% completion` : undefined}
          icon={<CheckCircle2 size={20} />}
          colorScheme="green"
          loading={loadAppts}
        />

        {can('patients:read') && (
          <KPICard
            label="Available doctors"
            value={loadWork ? '—' : availDoctors}
            subvalue="accepting patients"
            icon={<Stethoscope size={20} />}
            colorScheme="teal"
            onClick={() => navigate('/appointments')}
            loading={loadWork}
          />
        )}

        {can('pharmacy:read') && (
          <KPICard
            label="Stock alerts"
            value={loadStock ? '—' : stockAlerts}
            subvalue={stockAlerts > 0 ? 'drugs below reorder' : 'all levels OK'}
            icon={<Pill size={20} />}
            colorScheme={stockAlerts > 0 ? 'amber' : 'green'}
            alert={stockAlerts > 0}
            onClick={() => navigate('/pharmacy')}
            loading={loadStock}
          />
        )}

        {can('billing:read') && (
          <KPICard
            label="Outstanding bills"
            value="—"
            icon={<FileText size={20} />}
            colorScheme="purple"
            onClick={() => navigate('/billing')}
          />
        )}
      </div>

      {/* ── Progress bar row ─────────────────────────────────────── */}
      {!loadAppts && totalToday > 0 && (
        <div className="grid sm:grid-cols-3 gap-4 bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <CapacityBar label="Booked"      current={bookedCount}  max={totalToday} color="blue"  />
          <CapacityBar label="In progress" current={activeCount}  max={totalToday} color="amber" />
          <CapacityBar label="Completed"   current={doneCount}    max={totalToday} color="green" />
        </div>
      )}

      {/* ── Main grid ────────────────────────────────────────────── */}
      <div className="grid lg:grid-cols-3 gap-6">

        {/* ── Today's schedule (2/3 width) ─────────────────────── */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900 flex items-center gap-2">
              <Clock size={16} className="text-slate-400" />
              Today's schedule
            </h2>
            <button onClick={() => navigate('/appointments')}
              className="text-xs text-blue-600 hover:text-blue-700 font-medium">
              Full schedule →
            </button>
          </div>

          {loadAppts ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : !todayAppts?.length ? (
            <EmptyState
              icon={<Calendar size={32} />}
              title="No appointments today"
              description="The schedule is clear for today."
              action={can('appointments:write') ? (
                <Button size="sm" variant="secondary" onClick={() => setBookOpen(true)}>
                  <Plus size={13} /> Book appointment
                </Button>
              ) : undefined}
            />
          ) : (
            <div className="divide-y divide-slate-50 max-h-[420px] overflow-y-auto">
              {todayAppts
                .sort((a: any, b: any) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
                .map((appt: any) => (
                  <button
                    key={appt.id}
                    onClick={() => navigate('/appointments')}
                    className={clsx(
                      'w-full flex items-center gap-3 px-5 py-3.5 text-left',
                      'hover:bg-slate-50 transition-colors',
                      PRIORITY_LEFT[appt.priority],
                    )}
                  >
                    {/* Time */}
                    <div className="flex-shrink-0 w-12 text-center">
                      <p className="text-sm font-bold font-mono text-slate-800">
                        {fmt.time(appt.scheduled_at)}
                      </p>
                      <p className="text-[10px] text-slate-400">{appt.duration_minutes}m</p>
                    </div>

                    {/* Details */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{appt.patient_name}</p>
                      {appt.doctor_name && (
                        <p className="text-xs text-slate-400 truncate flex items-center gap-1">
                          <Stethoscope size={10} /> {appt.doctor_name}
                        </p>
                      )}
                    </div>

                    {/* Type pill */}
                    <span className="flex-shrink-0 text-xs text-slate-400 capitalize hidden sm:block">
                      {appt.appointment_type?.replace('_', ' ')}
                    </span>

                    {/* Status */}
                    <StatusBadge status={appt.status} />
                  </button>
                ))
              }
            </div>
          )}
        </div>

        {/* ── Side panel (1/3 width) ───────────────────────────── */}
        <div className="space-y-5">

          {/* Doctor workload */}
          {can('patients:read') && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2">
                  <Activity size={15} className="text-slate-400" /> Doctor workload
                </h3>
              </div>
              <div className="p-4 space-y-3">
                {loadWork ? (
                  <div className="flex justify-center py-4"><Spinner size="sm" /></div>
                ) : !workload?.length ? (
                  <p className="text-sm text-slate-400 text-center py-2">No doctors on duty.</p>
                ) : (
                  workload.slice(0, 5).map((doc: any) => (
                    <div key={doc.id}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-medium text-slate-700 truncate max-w-36">{doc.full_name}</span>
                        <span className={clsx(
                          'text-xs font-medium',
                          doc.is_fully_booked ? 'text-red-500' : 'text-slate-400',
                        )}>
                          {doc.todays_count}/{doc.max_patients_per_day}
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={clsx(
                            'h-full rounded-full transition-all duration-300',
                            doc.is_fully_booked
                              ? 'bg-red-500'
                              : doc.todays_count / doc.max_patients_per_day > 0.75
                                ? 'bg-amber-400'
                                : 'bg-blue-500',
                          )}
                          style={{ width: `${Math.min((doc.todays_count / doc.max_patients_per_day) * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Stock alerts */}
          {can('pharmacy:read') && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
                <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2">
                  <AlertTriangle size={14} className="text-amber-500" /> Stock alerts
                </h3>
                <button onClick={() => navigate('/pharmacy')}
                  className="text-xs text-blue-600 hover:text-blue-700 font-medium">View →</button>
              </div>
              <div className="divide-y divide-slate-50 max-h-52 overflow-y-auto">
                {loadStock ? (
                  <div className="flex justify-center py-6"><Spinner size="sm" /></div>
                ) : !lowStock?.results?.length ? (
                  <div className="flex items-center gap-2 px-4 py-4 text-sm text-green-600">
                    <CheckCircle2 size={15} /> All stock levels OK
                  </div>
                ) : (
                  lowStock.results.slice(0, 6).map((drug: any) => (
                    <div key={drug.id}
                      onClick={() => navigate('/pharmacy')}
                      className="flex items-center gap-2.5 px-4 py-2.5 hover:bg-slate-50 cursor-pointer">
                      <span className={clsx(
                        'w-2 h-2 rounded-full flex-shrink-0',
                        drug.stock_quantity === 0 ? 'bg-red-500' : 'bg-amber-400',
                      )} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-800 truncate">{drug.name}</p>
                        <p className="text-[10px] text-slate-400">{drug.generic_name}</p>
                      </div>
                      <span className={clsx(
                        'text-xs font-bold flex-shrink-0',
                        drug.stock_quantity === 0 ? 'text-red-600' : 'text-amber-600',
                      )}>
                        {drug.stock_quantity}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Quick book modal */}
      <Modal isOpen={bookOpen} onClose={() => setBookOpen(false)} title="Book appointment" size="lg">
        <AppointmentBookingForm
          onSuccess={() => { setBookOpen(false); }}
          onCancel={() => setBookOpen(false)}
        />
      </Modal>
    </div>
  );
}
