import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { patientService } from '../../services/patientService';
import { useQuery } from '../../hooks/useApi';
import { PatientForm } from '../../components/forms/PatientForm';
import { Spinner, Alert } from '../../components/ui';
import { ArrowLeft } from 'lucide-react';
import { Patient } from '../../types';

export function EditPatientPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: patient, loading, error } = useQuery(() => patientService.get(id!), [id]);

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(`/patients/${id}`)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {patient ? `Edit — ${patient.full_name}` : 'Edit patient'}
          </h1>
          {patient && <p className="text-sm text-slate-500 font-mono mt-0.5">{patient.mrn}</p>}
        </div>
      </div>
      {loading && <div className="flex justify-center py-12"><Spinner size="lg" /></div>}
      {error   && <Alert variant="error">{error}</Alert>}
      {patient && (
        <PatientForm
          initialData={patient}
          onSuccess={(p: Patient) => navigate(`/patients/${p.id}`)}
        />
      )}
    </div>
  );
}
