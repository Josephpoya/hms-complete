import api from './api';
import { Drug, Prescription, PaginatedResponse } from '../types';

export const pharmacyService = {
  drugs: {
    list: (params?: Record<string, any>) =>
      api.get<PaginatedResponse<Drug>>('/pharmacy/drugs/', { params }).then(r => r.data),
    get: (id: string) =>
      api.get<Drug>(`/pharmacy/drugs/${id}/`).then(r => r.data),
    lowStock: () =>
      api.get<PaginatedResponse<Drug>>('/pharmacy/drugs/low-stock/').then(r => r.data),
    expiring: (days = 30) =>
      api.get<PaginatedResponse<Drug>>('/pharmacy/drugs/expiring/', { params: { days } }).then(r => r.data),
    restock: (id: string, quantity: number, batch_number?: string, expiry_date?: string) =>
      api.post<Drug>(`/pharmacy/drugs/${id}/restock/`, { quantity, batch_number, expiry_date }).then(r => r.data),
  },

  prescriptions: {
    list: (params?: Record<string, any>) =>
      api.get<PaginatedResponse<Prescription>>('/pharmacy/prescriptions/', { params }).then(r => r.data),
    get: (id: string) =>
      api.get<Prescription>(`/pharmacy/prescriptions/${id}/`).then(r => r.data),
    create: (data: Partial<Prescription>) =>
      api.post<Prescription>('/pharmacy/prescriptions/', data).then(r => r.data),
    dispense: (id: string, notes?: string) =>
      api.post<Prescription>(`/pharmacy/prescriptions/${id}/dispense/`, { notes }).then(r => r.data),
    cancel: (id: string, reason: string) =>
      api.post<Prescription>(`/pharmacy/prescriptions/${id}/cancel/`, { reason }).then(r => r.data),
  },
};
