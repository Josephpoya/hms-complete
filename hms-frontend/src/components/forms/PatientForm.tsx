/**
 * components/forms/PatientForm.tsx
 * =================================
 * Reusable form for both creating and editing a patient.
 * Validates all fields client-side before submitting;
 * maps server-side field errors back to the correct field.
 */

import React, { useState, useEffect } from 'react';
import { Patient } from '../../types';
import { patientService } from '../../services/patientService';
import { Button, Alert, Card, CardHeader, CardContent, Input, Select } from '../ui';
import { toast } from '../../hooks/useApi';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';

interface Props {
  initialData?: Patient;
  onSuccess?: (p: Patient) => void;
}

type FormData = {
  first_name: string; last_name: string; date_of_birth: string;
  gender: string; blood_type: string; nationality: string;
  phone: string; email: string; address: string; national_id: string;
  allergies: string; chronic_conditions: string;
  is_diabetic: boolean; is_hypertensive: boolean;
  emergency_contact_name: string; emergency_contact_phone: string;
  emergency_contact_relation: string;
  insurance_provider: string; insurance_number: string; insurance_expiry: string;
};

const EMPTY: FormData = {
  first_name: '', last_name: '', date_of_birth: '', gender: '', blood_type: '',
  nationality: '', phone: '', email: '', address: '', national_id: '',
  allergies: '', chronic_conditions: '', is_diabetic: false, is_hypertensive: false,
  emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
  insurance_provider: '', insurance_number: '', insurance_expiry: '',
};

export function PatientForm({ initialData, onSuccess }: Props) {
  const navigate = useNavigate();
  const { can }  = useAuth();
  const isEdit   = !!initialData;

  const [form,       setForm]       = useState<FormData>(EMPTY);
  const [errors,     setErrors]     = useState<Partial<Record<keyof FormData, string>>>({});
  const [serverError, setServerError] = useState('');
  const [saving,     setSaving]     = useState(false);

  useEffect(() => {
    if (initialData) {
      setForm({
        first_name: initialData.first_name ?? '',
        last_name:  initialData.last_name  ?? '',
        date_of_birth: initialData.date_of_birth ?? '',
        gender:     initialData.gender     ?? '',
        blood_type: initialData.blood_type ?? '',
        nationality: initialData?.nationality ?? '',
        phone:       initialData.phone      ?? '',
        email:       initialData.email      ?? '',
        address:     initialData.address    ?? '',
        national_id: initialData?.national_id ?? '',
        allergies:   initialData.allergies  ?? '',
        chronic_conditions: initialData.chronic_conditions ?? '',
        is_diabetic:    initialData.is_diabetic    ?? false,
        is_hypertensive: initialData.is_hypertensive ?? false,
        emergency_contact_name:     initialData.emergency_contact_name     ?? '',
        emergency_contact_phone:    initialData.emergency_contact_phone    ?? '',
        emergency_contact_relation: initialData.emergency_contact_relation ?? '',
        insurance_provider: initialData.insurance_provider ?? '',
        insurance_number:   initialData.insurance_number   ?? '',
        insurance_expiry:   initialData.insurance_expiry   ?? '',
      });
    }
  }, [initialData]);

  function set<K extends keyof FormData>(key: K, value: FormData[K]) {
    setForm(f => ({ ...f, [key]: value }));
    setErrors(e => ({ ...e, [key]: '' }));
  }

  function validate(): boolean {
    const e: Partial<Record<keyof FormData, string>> = {};
    if (!form.first_name.trim()) e.first_name = 'First name is required.';
    if (!form.last_name.trim())  e.last_name  = 'Last name is required.';
    if (!form.date_of_birth)     e.date_of_birth = 'Date of birth is required.';
    else if (new Date(form.date_of_birth) >= new Date()) e.date_of_birth = 'Date of birth must be in the past.';
    if (!form.gender)            e.gender     = 'Gender is required.';
    if (!form.phone.trim())      e.phone      = 'Phone number is required.';
    else if (!/^\+?[0-9]{7,15}$/.test(form.phone.replace(/[\s\-().]/g, '')))
      e.phone = 'Enter a valid phone number.';
    if (form.email && !/\S+@\S+\.\S+/.test(form.email))
      e.email = 'Enter a valid email address.';
    if (form.emergency_contact_name && !form.emergency_contact_phone)
      e.emergency_contact_phone = 'Phone is required when a contact name is provided.';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    setSaving(true);
    setServerError('');

    const payload: Record<string, unknown> = {
      ...form,
      blood_type:  form.blood_type  || null,
      national_id: form.national_id || null,
      email:       form.email       || null,
    };

    try {
      let result: Patient;
      if (isEdit && initialData) {
        result = await patientService.update(initialData.id, payload);
        toast('Patient record updated.', 'success');
      } else {
        result = await patientService.create(payload);
        toast(`Patient registered — MRN: ${result.mrn}`, 'success');
      }
      onSuccess?.(result);
      if (!onSuccess) navigate(`/patients/${result.id}`);
    } catch (err: any) {
      if (err?.fields) {
        const fe: Partial<Record<keyof FormData, string>> = {};
        for (const [k, v] of Object.entries(err.fields)) {
          fe[k as keyof FormData] = Array.isArray(v) ? v[0] : String(v);
        }
        setErrors(fe);
      } else {
        setServerError(err?.message ?? 'Failed to save patient record.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6 max-w-4xl">
      {serverError && <Alert variant="error">{serverError}</Alert>}

      {/* Personal details */}
      <Card>
        <CardHeader>
          <h2 className="font-semibold text-slate-800">Personal information</h2>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input label="First name *" id="first_name" value={form.first_name}
            onChange={e => set('first_name', e.target.value)} error={errors.first_name} />
          <Input label="Last name *" id="last_name" value={form.last_name}
            onChange={e => set('last_name', e.target.value)} error={errors.last_name} />
          <Input label="Date of birth *" id="dob" type="date" value={form.date_of_birth}
            onChange={e => set('date_of_birth', e.target.value)} error={errors.date_of_birth} />
          <Select label="Gender *" id="gender" value={form.gender}
            onChange={e => set('gender', e.target.value)} error={errors.gender}>
            <option value="">Select gender…</option>
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="other">Other</option>
            <option value="prefer_not_to_say">Prefer not to say</option>
          </Select>
          <Select label="Blood type" id="blood_type" value={form.blood_type}
            onChange={e => set('blood_type', e.target.value)}>
            <option value="">Unknown</option>
            {['A+','A-','B+','B-','AB+','AB-','O+','O-'].map(t => <option key={t}>{t}</option>)}
          </Select>
          <Input label="Nationality" id="nationality" value={form.nationality}
            onChange={e => set('nationality', e.target.value)} />
          <Input label="National ID / Passport" id="national_id" value={form.national_id}
            onChange={e => set('national_id', e.target.value)}
            placeholder="Encrypted at rest" error={errors.national_id} />
        </CardContent>
      </Card>

      {/* Contact */}
      <Card>
        <CardHeader><h2 className="font-semibold text-slate-800">Contact details</h2></CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input label="Phone *" id="phone" type="tel" value={form.phone}
            onChange={e => set('phone', e.target.value)} error={errors.phone}
            placeholder="+256700000000" />
          <Input label="Email" id="email" type="email" value={form.email}
            onChange={e => set('email', e.target.value)} error={errors.email} />
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-slate-700 mb-1">Address</label>
            <textarea value={form.address} onChange={e => set('address', e.target.value)}
              rows={2} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
          </div>
        </CardContent>
      </Card>

      {/* Clinical flags */}
      <Card>
        <CardHeader><h2 className="font-semibold text-slate-800">Clinical information</h2></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 bg-slate-50">
              <input type="checkbox" id="diabetic" checked={form.is_diabetic}
                onChange={e => set('is_diabetic', e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded" />
              <label htmlFor="diabetic" className="text-sm font-medium text-slate-700">Diabetic</label>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 bg-slate-50">
              <input type="checkbox" id="hypertensive" checked={form.is_hypertensive}
                onChange={e => set('is_hypertensive', e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded" />
              <label htmlFor="hypertensive" className="text-sm font-medium text-slate-700">Hypertensive</label>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Known allergies</label>
            <textarea value={form.allergies} onChange={e => set('allergies', e.target.value)}
              rows={2} placeholder="List known allergens, or leave blank if none"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Chronic conditions</label>
            <textarea value={form.chronic_conditions} onChange={e => set('chronic_conditions', e.target.value)}
              rows={2} placeholder="Pre-existing conditions"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
          </div>
        </CardContent>
      </Card>

      {/* Emergency contact */}
      <Card>
        <CardHeader><h2 className="font-semibold text-slate-800">Emergency contact</h2></CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Input label="Full name" id="ec_name" value={form.emergency_contact_name}
            onChange={e => set('emergency_contact_name', e.target.value)} />
          <Input label="Phone" id="ec_phone" type="tel" value={form.emergency_contact_phone}
            onChange={e => set('emergency_contact_phone', e.target.value)}
            error={errors.emergency_contact_phone} />
          <Input label="Relationship" id="ec_rel" value={form.emergency_contact_relation}
            onChange={e => set('emergency_contact_relation', e.target.value)}
            placeholder="Spouse, parent, sibling…" />
        </CardContent>
      </Card>

      {/* Insurance */}
      <Card>
        <CardHeader><h2 className="font-semibold text-slate-800">Insurance</h2></CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Input label="Provider" id="ins_provider" value={form.insurance_provider}
            onChange={e => set('insurance_provider', e.target.value)} />
          <Input label="Policy number" id="ins_number" value={form.insurance_number}
            onChange={e => set('insurance_number', e.target.value)} />
          <Input label="Expiry date" id="ins_expiry" type="date" value={form.insurance_expiry}
            onChange={e => set('insurance_expiry', e.target.value)} />
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-between pt-2">
        <button type="button" onClick={() => navigate(-1)}
          className="text-sm text-slate-500 hover:text-slate-700 transition-colors">
          ← Cancel
        </button>
        <Button type="submit" isLoading={saving} size="lg">
          {isEdit ? 'Save changes' : 'Register patient'}
        </Button>
      </div>
    </form>
  );
}
