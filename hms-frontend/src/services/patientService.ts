import api from './api';
import { Patient, PatientMinimal, PaginatedResponse } from '../types';

export interface PatientFilters {
  search?: string; gender?: string; blood_type?: string;
  is_active?: boolean; page?: number; page_size?: number; ordering?: string;
}

export const patientService = {
  list: (params?: PatientFilters) =>
    api.get<PaginatedResponse<Patient>>('/patients/', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<Patient>(`/patients/${id}/`).then(r => r.data),

  create: (data: Partial<Patient>) =>
    api.post<Patient>('/patients/', data).then(r => r.data),

  update: (id: string, data: Partial<Patient>) =>
    api.patch<Patient>(`/patients/${id}/`, data).then(r => r.data),

  deactivate: (id: string, reason?: string) =>
    api.delete(`/patients/${id}/`, { data: { reason } }),

  search: (q: string) =>
    api.get<PatientMinimal[]>('/patients/search/', { params: { q } }).then(r => r.data),

  export: () =>
    api.get('/patients/export/', { responseType: 'blob' }).then(r => r.data),
};
