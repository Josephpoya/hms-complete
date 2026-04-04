import api from './api';
import { Invoice, InvoiceItem, PaginatedResponse } from '../types';

export const billingService = {
  list: (params?: Record<string, any>) =>
    api.get<PaginatedResponse<Invoice>>('/billing/invoices/', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<Invoice>(`/billing/invoices/${id}/`).then(r => r.data),

  create: (data: Partial<Invoice> & { items?: Partial<InvoiceItem>[] }) =>
    api.post<Invoice>('/billing/invoices/', data).then(r => r.data),

  update: (id: string, data: Partial<Invoice>) =>
    api.patch<Invoice>(`/billing/invoices/${id}/`, data).then(r => r.data),

  action: (id: string, action: 'issue' | 'mark_overdue' | 'void') =>
    api.post<Invoice>(`/billing/invoices/${id}/action/`, { action }).then(r => r.data),

  recordPayment: (id: string, amount: string, payment_method: string, notes?: string) =>
    api.post<Invoice>(`/billing/invoices/${id}/payment/`, { amount, payment_method, notes }).then(r => r.data),

  addItem: (invoiceId: string, item: Partial<InvoiceItem>) =>
    api.post<InvoiceItem>(`/billing/invoices/${invoiceId}/items/`, item).then(r => r.data),

  removeItem: (invoiceId: string, itemId: string) =>
    api.delete(`/billing/invoices/${invoiceId}/items/${itemId}/`),
};
