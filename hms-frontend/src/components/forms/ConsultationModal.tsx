/**
 * components/forms/ConsultationModal.tsx
 * ========================================
 * Opens when a doctor clicks "Start" on an appointment (in_progress).
 * Tabs: SOAP Notes | Vitals | Prescriptions
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { Appointment } from '../../types';
import { recordService, MedicalRecord, CreateMedicalRecordPayload, Vitals } from '../../services/recordService';
import { pharmacyService } from '../../services/pharmacyService';
import { Modal, Button, Alert, Spinner } from '../ui';
import { toast } from '../../hooks/useApi';
import { Drug, Prescription } from '../../types';
import {
  FileText, Activity, Pill, Plus, Trash2, Save, CheckCircle,
} from 'lucide-react';
import { clsx } from 'clsx';

// ─── Types ────────────────────────────────────────────────────────────────────

interface PrescriptionDraft {
  drug_id: string;
  drug_name: string;
  dosage: string;
  frequency: string;
  duration_days: number;
  quantity_prescribed: number;
  instructions: string;
  route: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  appointment: Appointment;
  onConsultationSaved?: () => void;
}

type Tab = 'soap' | 'vitals' | 'prescriptions';

// ─── Subcomponents ────────────────────────────────────────────────────────────

function TabButton({ active, onClick, icon, label, count }: {
  active: boolean; onClick: () => void;
  icon: React.ReactNode; label: string; count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-all',
        active
          ? 'bg-blue-600 text-white shadow-sm'
          : 'text-slate-600 hover:bg-slate-100',
      )}
    >
      {icon}
      {label}
      {count !== undefined && count > 0 && (
        <span className={clsx(
          'ml-1 text-xs px-1.5 py-0.5 rounded-full font-semibold',
          active ? 'bg-blue-500 text-white' : 'bg-slate-200 text-slate-600',
        )}>{count}</span>
      )}
    </button>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
      {children}
    </label>
  );
}

function TextArea({
  value, onChange, placeholder, rows = 4, disabled,
}: {
  value: string; onChange: (v: string) => void;
  placeholder?: string; rows?: number; disabled?: boolean;
}) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      disabled={disabled}
      className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-400 resize-none disabled:bg-slate-50 disabled:text-slate-400 transition-colors"
    />
  );
}

function VitalInput({
  label, unit, value, onChange, placeholder,
}: {
  label: string; unit?: string; value: string;
  onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <SectionLabel>{label}{unit && <span className="ml-1 normal-case font-normal text-slate-400">({unit})</span>}</SectionLabel>
      <div className="relative">
        <input
          type="number"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-400 transition-colors"
        />
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function ConsultationModal({ isOpen, onClose, appointment, onConsultationSaved }: Props) {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>('soap');

  // SOAP state
  const [record, setRecord] = useState<MedicalRecord | null>(null);
  const [recordLoading, setRecordLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [soap, setSoap] = useState({
    subjective: '', objective: '', assessment: '', plan: '',
    icd10_code: '', icd10_description: '', follow_up_date: '',
    referral_to: '', referral_notes: '',
  });

  // Vitals state
  const [vitals, setVitals] = useState<Record<string, string>>({});

  // Prescription state
  const [drugs, setDrugs] = useState<Drug[]>([]);
  const [drugsLoading, setDrugsLoading] = useState(false);
  const [drugSearch, setDrugSearch] = useState('');
  const [prescriptions, setPrescriptions] = useState<PrescriptionDraft[]>([]);
  const [savedPrescriptions, setSavedPrescriptions] = useState<Prescription[]>([]);
  const [prescSaving, setPrescSaving] = useState(false);

  // ── Load existing record on open ──────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    setTab('soap');
    setSaveError('');
    loadExistingRecord();
    loadSavedPrescriptions();
  }, [isOpen, appointment.id]);

  async function loadExistingRecord() {
    setRecordLoading(true);
    try {
      const resp = await recordService.forAppointment(appointment.id) as any;
      const results = resp.results ?? [];
      if (results.length > 0) {
        const r: MedicalRecord = results[0];
        setRecord(r);
        setSoap({
          subjective: r.subjective ?? '',
          objective: r.objective ?? '',
          assessment: r.assessment ?? '',
          plan: r.plan ?? '',
          icd10_code: r.icd10_code ?? '',
          icd10_description: r.icd10_description ?? '',
          follow_up_date: r.follow_up_date ?? '',
          referral_to: r.referral_to ?? '',
          referral_notes: r.referral_notes ?? '',
        });
        // Convert vitals numbers to strings for inputs
        const v: Record<string, string> = {};
        if (r.vitals) {
          Object.entries(r.vitals).forEach(([k, val]) => {
            if (val !== undefined && val !== null) v[k] = String(val);
          });
        }
        setVitals(v);
      } else {
        setRecord(null);
        setSoap({ subjective: '', objective: '', assessment: '', plan: '', icd10_code: '', icd10_description: '', follow_up_date: '', referral_to: '', referral_notes: '' });
        setVitals({});
      }
    } catch {
      // no record yet
    } finally {
      setRecordLoading(false);
    }
  }

  async function loadSavedPrescriptions() {
    try {
      const resp = await pharmacyService.prescriptions.list({ appointment: appointment.id });
      setSavedPrescriptions(resp.results ?? []);
    } catch {
      setSavedPrescriptions([]);
    }
  }

  // ── Drug search ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (tab !== 'prescriptions') return;
    setDrugsLoading(true);
    pharmacyService.drugs.list({ search: drugSearch, is_active: true, page_size: 20 })
      .then(r => setDrugs(r.results ?? []))
      .catch(() => setDrugs([]))
      .finally(() => setDrugsLoading(false));
  }, [tab, drugSearch]);

  // ── Save SOAP + vitals ────────────────────────────────────────────────────
  async function saveSoap() {
    setSaving(true);
    setSaveError('');
    try {
      // Parse vitals — only include filled fields
      const parsedVitals: Vitals = {};
      Object.entries(vitals).forEach(([k, v]) => {
        if (v !== '') (parsedVitals as any)[k] = parseFloat(v);
      });

      const payload: CreateMedicalRecordPayload = {
        patient: appointment.patient,
        doctor: user?.doctor_profile ?? '',
        appointment: appointment.id,
        ...soap,
        vitals: Object.keys(parsedVitals).length > 0 ? parsedVitals : undefined,
      };

      if (record && !record.is_locked) {
        await recordService.update(record.id, payload);
        toast('Notes updated.', 'success');
      } else if (!record) {
        const created = await recordService.create(payload);
        setRecord(created);
        toast('Notes saved.', 'success');
      } else {
        setSaveError('This record is locked and cannot be edited.');
      }
    } catch (e: any) {
      setSaveError(e?.message ?? 'Failed to save notes.');
    } finally {
      setSaving(false);
    }
  }

  // ── Add prescription draft ────────────────────────────────────────────────
  function addDrug(drug: Drug) {
    if (prescriptions.find(p => p.drug_id === drug.id)) return;
    setPrescriptions(prev => [...prev, {
      drug_id: drug.id,
      drug_name: drug.name,
      dosage: drug.strength ?? '',
      frequency: 'twice daily',
      duration_days: 7,
      quantity_prescribed: 14,
      instructions: '',
      route: 'oral',
    }]);
  }

  function updateDraft(index: number, field: keyof PrescriptionDraft, value: string | number) {
    setPrescriptions(prev => prev.map((p, i) => i === index ? { ...p, [field]: value } : p));
  }

  function removeDraft(index: number) {
    setPrescriptions(prev => prev.filter((_, i) => i !== index));
  }

  // ── Save prescriptions ────────────────────────────────────────────────────
  async function savePrescriptions() {
    if (!record && !appointment.id) {
      toast('Save SOAP notes first to link prescriptions.', 'error');
      return;
    }
    setPrescSaving(true);
    try {
      for (const draft of prescriptions) {
        await pharmacyService.prescriptions.create({
          patient: appointment.patient,
          doctor: user?.doctor_profile ?? '',
          medical_record: record?.id,
          drug: draft.drug_id,
          dosage: draft.dosage,
          frequency: draft.frequency,
          duration_days: draft.duration_days,
          quantity_prescribed: draft.quantity_prescribed,
          instructions: draft.instructions,
          route: draft.route,
        } as any);
      }
      toast(`${prescriptions.length} prescription(s) saved.`, 'success');
      setPrescriptions([]);
      loadSavedPrescriptions();
    } catch (e: any) {
      toast(e?.message ?? 'Failed to save prescriptions.', 'error');
    } finally {
      setPrescSaving(false);
    }
  }

  const vitalFields: { key: keyof Vitals; label: string; unit: string; placeholder: string }[] = [
    { key: 'bp_systolic',      label: 'Systolic BP',    unit: 'mmHg', placeholder: '120' },
    { key: 'bp_diastolic',     label: 'Diastolic BP',   unit: 'mmHg', placeholder: '80' },
    { key: 'pulse',            label: 'Pulse',           unit: 'bpm',  placeholder: '72' },
    { key: 'temperature',      label: 'Temperature',     unit: '°C',   placeholder: '36.6' },
    { key: 'spo2',             label: 'SpO₂',            unit: '%',    placeholder: '98' },
    { key: 'respiratory_rate', label: 'Resp. Rate',      unit: '/min', placeholder: '16' },
    { key: 'weight_kg',        label: 'Weight',          unit: 'kg',   placeholder: '70' },
    { key: 'height_cm',        label: 'Height',          unit: 'cm',   placeholder: '170' },
    { key: 'blood_glucose',    label: 'Blood Glucose',   unit: 'mmol/L', placeholder: '5.5' },
  ];

  const isLocked = record?.is_locked ?? false;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Consultation — ${appointment.patient_name}`}
      size="xl"
    >
      {/* Patient info strip */}
      <div className="flex items-center gap-4 mb-4 p-3 bg-slate-50 rounded-lg border border-slate-100 text-sm">
        <div>
          <span className="text-slate-500">MRN</span>
          <span className="ml-2 font-mono font-semibold text-slate-700">{appointment.patient_mrn ?? '—'}</span>
        </div>
        <div className="w-px h-4 bg-slate-200" />
        <div>
          <span className="text-slate-500">Doctor</span>
          <span className="ml-2 font-semibold text-slate-700">{appointment.doctor_name ?? '—'}</span>
        </div>
        <div className="w-px h-4 bg-slate-200" />
        <div>
          <span className="text-slate-500">Chief complaint</span>
          <span className="ml-2 text-slate-700">{appointment.chief_complaint ?? '—'}</span>
        </div>
        {isLocked && (
          <span className="ml-auto text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded font-medium">
            🔒 Record locked
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4">
        <TabButton active={tab === 'soap'} onClick={() => setTab('soap')}
          icon={<FileText size={14} />} label="SOAP Notes" />
        <TabButton active={tab === 'vitals'} onClick={() => setTab('vitals')}
          icon={<Activity size={14} />} label="Vitals" />
        <TabButton active={tab === 'prescriptions'} onClick={() => setTab('prescriptions')}
          icon={<Pill size={14} />} label="Prescriptions"
          count={prescriptions.length + savedPrescriptions.length} />
      </div>

      {recordLoading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : (
        <>
          {/* ── SOAP Tab ── */}
          {tab === 'soap' && (
            <div className="space-y-4">
              {saveError && <Alert variant="error">{saveError}</Alert>}

              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <SectionLabel>S — Subjective (Patient reports)</SectionLabel>
                  <TextArea value={soap.subjective} onChange={v => setSoap(s => ({ ...s, subjective: v }))}
                    placeholder="Chief complaint, symptom history, pain scale, duration…" disabled={isLocked} />
                </div>
                <div className="col-span-2">
                  <SectionLabel>O — Objective (Clinical findings)</SectionLabel>
                  <TextArea value={soap.objective} onChange={v => setSoap(s => ({ ...s, objective: v }))}
                    placeholder="Physical exam findings, observations, test results…" disabled={isLocked} />
                </div>
                <div className="col-span-2">
                  <SectionLabel>A — Assessment (Diagnosis)</SectionLabel>
                  <TextArea value={soap.assessment} onChange={v => setSoap(s => ({ ...s, assessment: v }))}
                    placeholder="Clinical reasoning and diagnosis…" rows={3} disabled={isLocked} />
                </div>
                <div className="col-span-2">
                  <SectionLabel>P — Plan (Treatment)</SectionLabel>
                  <TextArea value={soap.plan} onChange={v => setSoap(s => ({ ...s, plan: v }))}
                    placeholder="Medications, investigations, referrals, follow-up…" rows={3} disabled={isLocked} />
                </div>

                {/* ICD-10 */}
                <div>
                  <SectionLabel>ICD-10 Code</SectionLabel>
                  <input value={soap.icd10_code}
                    onChange={e => setSoap(s => ({ ...s, icd10_code: e.target.value }))}
                    placeholder="e.g. J06.9" disabled={isLocked}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:bg-slate-50" />
                </div>
                <div>
                  <SectionLabel>ICD-10 Description</SectionLabel>
                  <input value={soap.icd10_description}
                    onChange={e => setSoap(s => ({ ...s, icd10_description: e.target.value }))}
                    placeholder="e.g. Acute upper respiratory infection" disabled={isLocked}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:bg-slate-50" />
                </div>

                {/* Follow-up & Referral */}
                <div>
                  <SectionLabel>Follow-up Date</SectionLabel>
                  <input type="date" value={soap.follow_up_date}
                    onChange={e => setSoap(s => ({ ...s, follow_up_date: e.target.value }))}
                    disabled={isLocked}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:bg-slate-50" />
                </div>
                <div>
                  <SectionLabel>Referral To</SectionLabel>
                  <input value={soap.referral_to}
                    onChange={e => setSoap(s => ({ ...s, referral_to: e.target.value }))}
                    placeholder="Department or specialist" disabled={isLocked}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:bg-slate-50" />
                </div>
              </div>

              {!isLocked && (
                <div className="flex justify-end pt-2">
                  <Button onClick={saveSoap} isLoading={saving}>
                    <Save size={14} /> Save Notes
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* ── Vitals Tab ── */}
          {tab === 'vitals' && (
            <div>
              <div className="grid grid-cols-3 gap-4">
                {vitalFields.map(f => (
                  <VitalInput
                    key={f.key}
                    label={f.label}
                    unit={f.unit}
                    placeholder={f.placeholder}
                    value={vitals[f.key] ?? ''}
                    onChange={v => setVitals(prev => ({ ...prev, [f.key]: v }))}
                  />
                ))}
              </div>
              {!isLocked && (
                <div className="flex justify-end mt-4 pt-2 border-t border-slate-100">
                  <Button onClick={saveSoap} isLoading={saving}>
                    <Save size={14} /> Save Vitals
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* ── Prescriptions Tab ── */}
          {tab === 'prescriptions' && (
            <div className="space-y-4">
              {/* Saved prescriptions */}
              {savedPrescriptions.length > 0 && (
                <div>
                  <SectionLabel>Saved Prescriptions</SectionLabel>
                  <div className="space-y-2">
                    {savedPrescriptions.map(p => (
                      <div key={p.id} className="flex items-center gap-3 p-3 bg-green-50 rounded-lg border border-green-100 text-sm">
                        <CheckCircle size={14} className="text-green-600 flex-shrink-0" />
                        <div className="flex-1">
                          <span className="font-semibold text-slate-800">{p.drug_name}</span>
                          {p.drug_strength && <span className="ml-1 text-slate-500">{p.drug_strength}</span>}
                          <span className="ml-2 text-slate-600">{p.dosage} · {p.frequency} · {p.duration_days} days</span>
                        </div>
                        <span className={clsx(
                          'text-xs px-2 py-0.5 rounded-full font-medium capitalize',
                          p.status === 'pending' ? 'bg-amber-100 text-amber-700' :
                          p.status === 'dispensed' ? 'bg-green-100 text-green-700' :
                          'bg-slate-100 text-slate-600',
                        )}>{p.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Drug search */}
              <div>
                <SectionLabel>Add Drug</SectionLabel>
                <input
                  value={drugSearch}
                  onChange={e => setDrugSearch(e.target.value)}
                  placeholder="Search drug name or generic…"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 mb-2"
                />
                {drugsLoading ? (
                  <div className="flex justify-center py-4"><Spinner size="sm" /></div>
                ) : (
                  <div className="max-h-40 overflow-y-auto border border-slate-100 rounded-lg divide-y divide-slate-50">
                    {drugs.length === 0 ? (
                      <p className="text-sm text-slate-400 text-center py-4">No drugs found.</p>
                    ) : drugs.map(drug => (
                      <button key={drug.id} onClick={() => addDrug(drug)}
                        disabled={drug.is_out_of_stock || drug.is_expired || !!prescriptions.find(p => p.drug_id === drug.id)}
                        className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-blue-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-left">
                        <div>
                          <span className="font-medium text-slate-800">{drug.name}</span>
                          {drug.strength && <span className="ml-1.5 text-slate-500 text-xs">{drug.strength}</span>}
                          <span className="ml-1.5 text-slate-400 text-xs">({drug.generic_name})</span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {drug.is_out_of_stock && <span className="text-xs text-red-500">Out of stock</span>}
                          {drug.is_expired && <span className="text-xs text-red-500">Expired</span>}
                          {!drug.is_out_of_stock && !drug.is_expired && (
                            <span className="text-xs text-slate-400">Stock: {drug.stock_quantity}</span>
                          )}
                          <Plus size={14} className="text-blue-500" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Prescription drafts */}
              {prescriptions.length > 0 && (
                <div className="space-y-3">
                  <SectionLabel>New Prescriptions ({prescriptions.length})</SectionLabel>
                  {prescriptions.map((p, i) => (
                    <div key={p.drug_id} className="p-3 border border-slate-200 rounded-xl space-y-3 bg-white">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-800 text-sm">{p.drug_name}</span>
                        <button onClick={() => removeDraft(i)} className="text-red-400 hover:text-red-600 transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <SectionLabel>Dosage</SectionLabel>
                          <input value={p.dosage} onChange={e => updateDraft(i, 'dosage', e.target.value)}
                            placeholder="e.g. 500mg"
                            className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-200" />
                        </div>
                        <div>
                          <SectionLabel>Frequency</SectionLabel>
                          <select value={p.frequency} onChange={e => updateDraft(i, 'frequency', e.target.value)}
                            className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-200">
                            <option>once daily</option>
                            <option>twice daily</option>
                            <option>three times daily</option>
                            <option>four times daily</option>
                            <option>every 8 hours</option>
                            <option>every 6 hours</option>
                            <option>as needed</option>
                            <option>stat</option>
                          </select>
                        </div>
                        <div>
                          <SectionLabel>Route</SectionLabel>
                          <select value={p.route} onChange={e => updateDraft(i, 'route', e.target.value)}
                            className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-200">
                            <option value="oral">Oral</option>
                            <option value="IV">IV</option>
                            <option value="IM">IM</option>
                            <option value="topical">Topical</option>
                            <option value="sublingual">Sublingual</option>
                            <option value="inhaled">Inhaled</option>
                          </select>
                        </div>
                        <div>
                          <SectionLabel>Duration (days)</SectionLabel>
                          <input type="number" min={1} value={p.duration_days}
                            onChange={e => updateDraft(i, 'duration_days', parseInt(e.target.value))}
                            className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-200" />
                        </div>
                        <div>
                          <SectionLabel>Qty to dispense</SectionLabel>
                          <input type="number" min={1} value={p.quantity_prescribed}
                            onChange={e => updateDraft(i, 'quantity_prescribed', parseInt(e.target.value))}
                            className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-200" />
                        </div>
                        <div>
                          <SectionLabel>Instructions</SectionLabel>
                          <input value={p.instructions} onChange={e => updateDraft(i, 'instructions', e.target.value)}
                            placeholder="e.g. take with food"
                            className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-200" />
                        </div>
                      </div>
                    </div>
                  ))}
                  <div className="flex justify-end">
                    <Button onClick={savePrescriptions} isLoading={prescSaving}>
                      <Save size={14} /> Save {prescriptions.length} Prescription{prescriptions.length !== 1 ? 's' : ''}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Footer */}
      <div className="flex justify-between items-center mt-5 pt-4 border-t border-slate-100">
        <span className="text-xs text-slate-400">
          {record ? `Record created · ${record.is_locked ? 'Locked' : 'Editable for 24h'}` : 'No record yet'}
        </span>
        <Button variant="secondary" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  );
}
