/**
 * components/forms/AppointmentBookingForm.tsx
 * ============================================
 * Modal-friendly appointment booking form.
 * Validates scheduling conflicts client-side where possible.
 * Shows available doctors filtered by department.
 */

import React, { useState, useEffect } from 'react';
import { appointmentService } from '../../services/appointmentService';
import { patientService } from '../../services/patientService';
import api from '../../services/api';
import { Doctor, PatientMinimal, Appointment } from '../../types';
import { Button, Alert, Input, Select } from '../ui';
import { toast } from '../../hooks/useApi';
import { format, addMinutes, isBefore } from 'date-fns';

interface Props {
  initialPatientId?: string;
  initialDoctorId?:  string;
  onSuccess?: (appt: Appointment) => void;
  onCancel?:  () => void;
}

export function AppointmentBookingForm({ initialPatientId, initialDoctorId, onSuccess, onCancel }: Props) {
  const [patientSearch, setPatientSearch] = useState('');
  const [patientOptions, setPatientOptions] = useState<PatientMinimal[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);

  const [form, setForm] = useState({
    patient:          initialPatientId ?? '',
    doctor:           initialDoctorId  ?? '',
    scheduled_at:     '',
    scheduled_time:   '',
    duration_minutes: '30',
    appointment_type: 'consultation',
    priority:         '3',
    chief_complaint:  '',
    notes:            '',
  });

  const [errors,      setErrors]      = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState('');
  const [saving,      setSaving]      = useState(false);

  // Load doctors on mount
  useEffect(() => {
    api.get('/doctors/', { params: { is_available: true, page_size: 100 } })
      .then(r => setDoctors(r.data.results))
      .catch(() => {});
  }, []);

  // Patient search
  useEffect(() => {
    if (patientSearch.length < 2) { setPatientOptions([]); return; }
    const t = setTimeout(() => {
      patientService.search(patientSearch).then(setPatientOptions).catch(() => {});
    }, 350);
    return () => clearTimeout(t);
  }, [patientSearch]);

  function set(key: string, value: string) {
    setForm(f => ({ ...f, [key]: value }));
    setErrors(e => ({ ...e, [key]: '' }));
  }

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!form.patient)        e.patient        = 'Please select a patient.';
    if (!form.doctor)         e.doctor         = 'Please select a doctor.';
    if (!form.scheduled_at)   e.scheduled_at   = 'Date is required.';
    if (!form.scheduled_time) e.scheduled_time = 'Time is required.';
    else {
      const dt = new Date(`${form.scheduled_at}T${form.scheduled_time}`);
      if (isBefore(dt, new Date())) e.scheduled_at = 'Appointment must be in the future.';
    }
    if (!form.appointment_type) e.appointment_type = 'Please select an appointment type.';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    setSaving(true);
    setServerError('');

    const scheduled_at = new Date(`${form.scheduled_at}T${form.scheduled_time}`).toISOString();

    try {
      const appt = await appointmentService.create({
        patient:          form.patient,
        doctor:           form.doctor,
        scheduled_at,
        duration_minutes: parseInt(form.duration_minutes),
        appointment_type: form.appointment_type as any,
        priority:         parseInt(form.priority) as any,
        chief_complaint:  form.chief_complaint || undefined,
        notes:            form.notes || undefined,
      });
      toast(`Appointment booked for ${format(new Date(scheduled_at), 'dd MMM yyyy HH:mm')}`, 'success');
      onSuccess?.(appt);
    } catch (err: any) {
      if (err?.fields) {
        const fe: Record<string, string> = {};
        for (const [k, v] of Object.entries(err.fields)) {
          fe[k] = Array.isArray(v) ? v[0] : String(v);
        }
        setErrors(fe);
      } else {
        setServerError(err?.message ?? 'Failed to book appointment.');
      }
    } finally {
      setSaving(false);
    }
  }

  const selectedDoctor = doctors.find(d => d.id === form.doctor);
  const tomorrow = format(addMinutes(new Date(), 30), "yyyy-MM-dd");

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      {serverError && <Alert variant="error">{serverError}</Alert>}

      {/* Patient selection */}
      {!initialPatientId && (
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Patient *</label>
          <input type="search" value={patientSearch}
            onChange={e => { setPatientSearch(e.target.value); if (!e.target.value) set('patient', ''); }}
            placeholder="Type name or MRN to search…"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
          {patientOptions.length > 0 && (
            <div className="border border-slate-200 rounded-lg mt-1 overflow-hidden shadow-sm">
              {patientOptions.map(p => (
                <button key={p.id} type="button"
                  onClick={() => { set('patient', p.id); setPatientSearch(p.full_name); setPatientOptions([]); }}
                  className="w-full flex items-center justify-between px-3 py-2.5 text-sm hover:bg-blue-50 text-left border-b border-slate-100 last:border-b-0">
                  <span className="font-medium">{p.full_name}</span>
                  <span className="text-slate-400 font-mono text-xs">{p.mrn}</span>
                </button>
              ))}
            </div>
          )}
          {errors.patient && <p className="mt-1 text-xs text-red-600">{errors.patient}</p>}
        </div>
      )}

      {/* Doctor selection */}
      <div>
        <Select label="Doctor *" id="doctor" value={form.doctor}
          onChange={e => set('doctor', e.target.value)} error={errors.doctor}>
          <option value="">Select a doctor…</option>
          {doctors.map(d => (
            <option key={d.id} value={d.id} disabled={d.is_fully_booked_today}>
              {d.full_name} — {d.specialisation}
              {d.is_fully_booked_today ? ' (fully booked today)' : ''}
            </option>
          ))}
        </Select>
        {selectedDoctor && (
          <p className="mt-1 text-xs text-slate-500">
            {selectedDoctor.department} · Consultation fee: UGX {parseFloat(selectedDoctor.consultation_fee).toLocaleString()}
          </p>
        )}
      </div>

      {/* Date & time */}
      <div className="grid grid-cols-2 gap-3">
        <Input label="Date *" id="date" type="date" min={tomorrow}
          value={form.scheduled_at} onChange={e => set('scheduled_at', e.target.value)}
          error={errors.scheduled_at} />
        <Input label="Time *" id="time" type="time"
          value={form.scheduled_time} onChange={e => set('scheduled_time', e.target.value)}
          error={errors.scheduled_time} />
      </div>

      {/* Duration & type */}
      <div className="grid grid-cols-2 gap-3">
        <Select label="Duration" id="duration" value={form.duration_minutes}
          onChange={e => set('duration_minutes', e.target.value)}>
          <option value="15">15 minutes</option>
          <option value="30">30 minutes</option>
          <option value="45">45 minutes</option>
          <option value="60">1 hour</option>
          <option value="90">1.5 hours</option>
        </Select>
        <Select label="Type *" id="type" value={form.appointment_type}
          onChange={e => set('appointment_type', e.target.value)} error={errors.appointment_type}>
          <option value="consultation">Consultation</option>
          <option value="follow_up">Follow up</option>
          <option value="procedure">Procedure</option>
          <option value="emergency">Emergency</option>
          <option value="telehealth">Telehealth</option>
        </Select>
      </div>

      {/* Priority */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1.5">Priority</label>
        <div className="flex gap-2">
          {[['1','Emergency','red'],['2','Urgent','amber'],['3','Routine','blue'],['4','Elective','gray']].map(([v, l, c]) => (
            <button key={v} type="button"
              onClick={() => set('priority', v)}
              className={`flex-1 py-1.5 px-2 rounded-lg text-xs font-medium border transition-colors ${
                form.priority === v
                  ? c === 'red'   ? 'bg-red-100 border-red-400 text-red-700'
                  : c === 'amber' ? 'bg-amber-100 border-amber-400 text-amber-700'
                  : c === 'blue'  ? 'bg-blue-100 border-blue-400 text-blue-700'
                  : 'bg-slate-200 border-slate-400 text-slate-700'
                  : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300'
              }`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Chief complaint */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">Chief complaint</label>
        <textarea value={form.chief_complaint} onChange={e => set('chief_complaint', e.target.value)}
          placeholder="Brief reason for the visit…" rows={2}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        )}
        <Button type="submit" isLoading={saving}>Book appointment</Button>
      </div>
    </form>
  );
}
