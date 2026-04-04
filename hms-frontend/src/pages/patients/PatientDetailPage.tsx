/**
 * pages/patients/PatientDetailPage.tsx
 * =====================================
 * Full patient profile view with:
 * - Demographics, clinical flags, contact, insurance
 * - Appointment history tab
 * - Medical records tab
 * - Quick actions (book appointment, create invoice)
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { patientService } from '../../services/patientService';
import { appointmentService } from '../../services/appointmentService';
import { useQuery } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import {
  Card, CardHeader, CardContent, Badge, StatusBadge,
  Button, Alert, Spinner, Table, Th, Td,
} from '../../components/ui';
import {
  ArrowLeft, Edit2, Calendar, FileText, Phone, Mail,
  MapPin, AlertTriangle, Shield, Heart, User, Activity,
  CheckCircle, XCircle, Clock,
} from 'lucide-react';
import { format, parseISO, differenceInYears } from 'date-fns';
import { clsx } from 'clsx';

type Tab = 'overview' | 'appointments' | 'records';

const BLOOD_COLOR: Record<string, string> = {
  'O+': 'text-red-700 bg-red-50', 'O-': 'text-red-800 bg-red-100',
  'A+': 'text-blue-700 bg-blue-50', 'A-': 'text-blue-800 bg-blue-100',
  'B+': 'text-green-700 bg-green-50', 'B-': 'text-green-800 bg-green-100',
  'AB+': 'text-purple-700 bg-purple-50', 'AB-': 'text-purple-800 bg-purple-100',
};

export function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { can }  = useAuth();
  const [tab, setTab] = useState<Tab>('overview');

  const { data: patient, loading, error } = useQuery(
    () => patientService.get(id!),
    [id],
  );

  const { data: appointments, loading: apptLoading } = useQuery(
    () => appointmentService.list({ patient: id, ordering: '-scheduled_at', page_size: 20 } as any),
    [id],
  );

  if (loading) {
    return <div className="flex justify-center py-24"><Spinner size="lg" /></div>;
  }
  if (error || !patient) {
    return <Alert variant="error">{error || 'Patient not found.'}</Alert>;
  }

  const age = differenceInYears(new Date(), parseISO(patient.date_of_birth));
  const hasAlerts = patient.is_diabetic || patient.is_hypertensive || patient.allergies;

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/patients')}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900">{patient.full_name}</h1>
              {!patient.is_active && <Badge variant="red">Inactive</Badge>}
            </div>
            <div className="flex items-center gap-3 mt-1">
              <span className="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded text-slate-600">
                {patient.mrn}
              </span>
              <span className="text-sm text-slate-500">{age} years old</span>
              <Badge variant={patient.gender === 'male' ? 'blue' : patient.gender === 'female' ? 'purple' : 'gray'}>
                {patient.gender}
              </Badge>
              {patient.blood_type && (
                <span className={clsx('text-xs font-bold px-2 py-0.5 rounded', BLOOD_COLOR[patient.blood_type] ?? 'bg-gray-100 text-gray-700')}>
                  {patient.blood_type}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {can('appointments:write') && (
            <Button variant="secondary" size="sm" onClick={() => navigate(`/appointments?patient=${patient.id}`)}>
              <Calendar size={14} /> Book appointment
            </Button>
          )}
          {can('patients:write') && (
            <Button size="sm" onClick={() => navigate(`/patients/${patient.id}/edit`)}>
              <Edit2 size={14} /> Edit
            </Button>
          )}
        </div>
      </div>

      {/* Clinical alerts banner */}
      {hasAlerts && (
        <div className="flex items-center gap-2 p-3.5 bg-amber-50 border border-amber-200 rounded-xl">
          <AlertTriangle size={16} className="text-amber-500 flex-shrink-0" />
          <div className="flex flex-wrap gap-2 text-sm">
            {patient.is_diabetic    && <Badge variant="amber">Diabetic</Badge>}
            {patient.is_hypertensive && <Badge variant="amber">Hypertensive</Badge>}
            {patient.allergies  && (
              <span className="text-amber-800">
                <strong>Allergies:</strong> {patient.allergies}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Outstanding balance */}
      {parseFloat(patient.outstanding_balance) > 0 && (
        <Alert variant="warning">
          Outstanding balance: <strong>UGX {parseFloat(patient.outstanding_balance).toLocaleString()}</strong>
        </Alert>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        {(['overview','appointments','records'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={clsx(
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize',
              tab === t ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900',
            )}>
            {t}
          </button>
        ))}
      </div>

      {/* ── Overview tab ─────────────────────────────────────────── */}
      {tab === 'overview' && (
        <div className="grid md:grid-cols-2 gap-5">
          {/* Contact */}
          <Card>
            <CardHeader><h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2"><Phone size={15} /> Contact</h3></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <InfoRow icon={<Phone size={13} />} label="Phone">{patient.phone}</InfoRow>
              {patient.email && <InfoRow icon={<Mail size={13} />} label="Email">{patient.email}</InfoRow>}
              {patient.address && <InfoRow icon={<MapPin size={13} />} label="Address">{patient.address}</InfoRow>}
            </CardContent>
          </Card>

          {/* Emergency contact */}
          <Card>
            <CardHeader><h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2"><User size={15} /> Emergency contact</h3></CardHeader>
            <CardContent className="text-sm">
              {patient.emergency_contact_name ? (
                <div className="space-y-2">
                  <InfoRow label="Name">{patient.emergency_contact_name}</InfoRow>
                  {patient.emergency_contact_phone && <InfoRow icon={<Phone size={13} />} label="Phone">{patient.emergency_contact_phone}</InfoRow>}
                  {patient.emergency_contact_relation && <InfoRow label="Relation">{patient.emergency_contact_relation}</InfoRow>}
                </div>
              ) : <p className="text-slate-400 text-sm">No emergency contact recorded.</p>}
            </CardContent>
          </Card>

          {/* Clinical */}
          <Card>
            <CardHeader><h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2"><Heart size={15} /> Clinical flags</h3></CardHeader>
            <CardContent className="space-y-2">
              <FlagRow label="Diabetic"       value={patient.is_diabetic} />
              <FlagRow label="Hypertensive"   value={patient.is_hypertensive} />
              {patient.chronic_conditions && (
                <div className="pt-2 border-t border-slate-100">
                  <p className="text-xs text-slate-500 mb-0.5">Chronic conditions</p>
                  <p className="text-sm text-slate-700">{patient.chronic_conditions}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Insurance */}
          <Card>
            <CardHeader><h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2"><Shield size={15} /> Insurance</h3></CardHeader>
            <CardContent className="text-sm">
              {patient.insurance_provider ? (
                <div className="space-y-2">
                  <InfoRow label="Provider">{patient.insurance_provider}</InfoRow>
                  {patient.insurance_number && <InfoRow label="Policy">{patient.insurance_number}</InfoRow>}
                  {patient.insurance_expiry && (
                    <InfoRow label="Expiry">
                      <span className="flex items-center gap-1.5">
                        {format(parseISO(patient.insurance_expiry), 'dd MMM yyyy')}
                        <Badge variant={patient.insurance_is_valid ? 'green' : 'red'}>
                          {patient.insurance_is_valid ? 'Valid' : 'Expired'}
                        </Badge>
                      </span>
                    </InfoRow>
                  )}
                </div>
              ) : <p className="text-slate-400">No insurance on file.</p>}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Appointments tab ─────────────────────────────────────── */}
      {tab === 'appointments' && (
        <Card>
          {apptLoading ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : !appointments?.results.length ? (
            <CardContent className="py-12 text-center text-slate-400">No appointments on record.</CardContent>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Date & time</Th>
                  <Th>Doctor</Th>
                  <Th>Type</Th>
                  <Th>Status</Th>
                  <Th>Duration</Th>
                </tr>
              </thead>
              <tbody>
                {appointments.results.map((appt: any) => (
                  <tr key={appt.id} className="hover:bg-slate-50">
                    <Td>
                      <p className="font-medium">{format(parseISO(appt.scheduled_at), 'dd MMM yyyy')}</p>
                      <p className="text-xs text-slate-500">{format(parseISO(appt.scheduled_at), 'HH:mm')}</p>
                    </Td>
                    <Td>{appt.doctor_name}</Td>
                    <Td><span className="capitalize text-sm">{appt.appointment_type?.replace('_', ' ')}</span></Td>
                    <Td><StatusBadge status={appt.status} /></Td>
                    <Td>{appt.duration_display}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {/* ── Records tab ──────────────────────────────────────────── */}
      {tab === 'records' && (
        <Card>
          <CardContent className="py-12 text-center text-slate-400">
            <Activity size={32} className="mx-auto mb-3 opacity-30" />
            <p className="font-medium">Medical records</p>
            <p className="text-sm mt-1">EHR viewer will be shown here.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Small helpers ────────────────────────────────────────────────────────────
function InfoRow({ icon, label, children }: { icon?: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      {icon && <span className="text-slate-400 mt-0.5 flex-shrink-0">{icon}</span>}
      <div>
        <span className="text-slate-400 text-xs block">{label}</span>
        <span className="text-slate-800">{children}</span>
      </div>
    </div>
  );
}

function FlagRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-slate-600">{label}</span>
      {value
        ? <CheckCircle size={16} className="text-green-500" />
        : <XCircle    size={16} className="text-slate-300" />}
    </div>
  );
}
