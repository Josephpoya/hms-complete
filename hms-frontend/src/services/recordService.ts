/**
 * services/recordService.ts
 * ==========================
 * Medical records (SOAP notes) API calls.
 */

import api from './api';
import { PaginatedResponse } from '../types';

export interface Vitals {
  bp_systolic?: number;
  bp_diastolic?: number;
  pulse?: number;
  temperature?: number;
  spo2?: number;
  respiratory_rate?: number;
  weight_kg?: number;
  height_cm?: number;
  bmi?: number;
  blood_glucose?: number;
  urine_output?: number;
}

export interface MedicalRecord {
  id: string;
  patient: string;
  patient_name?: string;
  doctor: string;
  doctor_name?: string;
  appointment?: string;
  subjective?: string;
  objective?: string;
  assessment?: string;
  plan?: string;
  icd10_code?: string;
  icd10_description?: string;
  vitals?: Vitals;
  follow_up_date?: string;
  referral_to?: string;
  referral_notes?: string;
  is_locked: boolean;
  recorded_at: string;
  updated_at: string;
}

export interface CreateMedicalRecordPayload {
  patient: string;
  doctor: string;
  appointment?: string;
  subjective?: string;
  objective?: string;
  assessment?: string;
  plan?: string;
  icd10_code?: string;
  icd10_description?: string;
  vitals?: Vitals;
  follow_up_date?: string;
  referral_to?: string;
  referral_notes?: string;
}

export const recordService = {
  list: (params?: Record<string, any>) =>
    api.get<PaginatedResponse<MedicalRecord>>('/records/', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<MedicalRecord>(`/records/${id}/`).then(r => r.data),

  create: (data: CreateMedicalRecordPayload) =>
    api.post<MedicalRecord>('/records/', data).then(r => r.data),

  update: (id: string, data: Partial<CreateMedicalRecordPayload>) =>
    api.patch<MedicalRecord>(`/records/${id}/`, data).then(r => r.data),

  forAppointment: (appointmentId: string) =>
    api.get<MedicalRecord>(`/records/?appointment=${appointmentId}`).then(r => r.data),

  forPatient: (patientId: string, params?: Record<string, any>) =>
    api.get<PaginatedResponse<MedicalRecord>>('/records/', {
      params: { patient: patientId, ...params },
    }).then(r => r.data),
};
