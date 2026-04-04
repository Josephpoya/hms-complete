import React from 'react';
import { useNavigate } from 'react-router-dom';
import { PatientForm } from '../../components/forms/PatientForm';
import { ArrowLeft } from 'lucide-react';
import { Patient } from '../../types';

export function NewPatientPage() {
  const navigate = useNavigate();
  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/patients')}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Register new patient</h1>
          <p className="text-sm text-slate-500 mt-0.5">All fields marked * are required</p>
        </div>
      </div>
      <PatientForm onSuccess={(p: Patient) => navigate(`/patients/${p.id}`)} />
    </div>
  );
}
