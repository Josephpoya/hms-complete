import api from './api';
import { Appointment, AppointmentCalendar, PaginatedResponse, AppointmentStatus } from '../types';

export interface AppointmentFilters {
  search?: string; status?: string; doctor?: string;
  patient?: string; scheduled_at__gte?: string;
  scheduled_at__lte?: string; page?: number; ordering?: string;
}

export const appointmentService = {
  list: (params?: AppointmentFilters) =>
    api.get<PaginatedResponse<Appointment>>('/appointments/', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<Appointment>(`/appointments/${id}/`).then(r => r.data),

  create: (data: Partial<Appointment>) =>
    api.post<Appointment>('/appointments/', data).then(r => r.data),

  update: (id: string, data: Partial<Appointment>) =>
    api.patch<Appointment>(`/appointments/${id}/`, data).then(r => r.data),

  changeStatus: (id: string, status: AppointmentStatus, cancellation_reason?: string) =>
    api.patch<Appointment>(`/appointments/${id}/status/`, { status, cancellation_reason }).then(r => r.data),

  today: (params?: Record<string, string>) =>
    api.get<AppointmentCalendar[]>('/appointments/today/', { params }).then(r => r.data),

  calendar: (params?: Record<string, string>) =>
    api.get<AppointmentCalendar[]>('/appointments/calendar/', { params }).then(r => r.data),
};
