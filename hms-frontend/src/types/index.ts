// ─── Auth ────────────────────────────────────────────────────────────────────
export type Role = 'admin' | 'doctor' | 'nurse' | 'receptionist';

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface TokenPayload {
  user_id: string;
  email: string;
  role: Role;
  mfa: boolean;
  exp: number;
  iat: number;
}

export interface User {
  id: string;
  email: string;
  role: Role;
  role_display: string;
  is_active: boolean;
  mfa_enabled: boolean;
  is_locked: boolean;
  doctor_profile: string | null;
  created_at: string;
  last_login: string | null;
}

// ─── API ─────────────────────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiError {
  error: {
    status_code: number;
    code: string;
    detail: string | Record<string, string[]>;
    request_id: string;
  };
}

// ─── Patients ─────────────────────────────────────────────────────────────────
export interface Patient {
  id: string;
  mrn: string;
  first_name: string;
  last_name: string;
  full_name: string;
  date_of_birth: string;
  age: number;
  gender: 'male' | 'female' | 'other' | 'prefer_not_to_say';
  blood_type?: string;
  phone: string;
  email?: string;
  address?: string;
  allergies?: string;
  chronic_conditions?: string;
  is_diabetic: boolean;
  is_hypertensive: boolean;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relation?: string;
  insurance_provider?: string;
  insurance_number?: string;
  insurance_expiry?: string;
  insurance_is_valid: boolean;
  outstanding_balance: string;
  is_active: boolean;
  created_at: string;
}

export interface PatientMinimal {
  id: string;
  mrn: string;
  full_name: string;
  phone: string;
}

// ─── Doctors ──────────────────────────────────────────────────────────────────
export interface Doctor {
  id: string;
  full_name: string;
  first_name: string;
  last_name: string;
  email: string;
  specialisation: string;
  department: string;
  qualification: string;
  consultation_fee: string;
  is_available: boolean;
  accepts_walk_in: boolean;
  todays_patient_count: number;
  licence_number: string;
  licence_expiry?: string;
  licence_is_valid: boolean;
  licence_expiring_soon: boolean;
  is_fully_booked_today: boolean;
}

// ─── Appointments ─────────────────────────────────────────────────────────────
export type AppointmentStatus =
  | 'booked' | 'checked_in' | 'in_progress'
  | 'completed' | 'cancelled' | 'no_show';

export type AppointmentType =
  | 'consultation' | 'follow_up' | 'procedure' | 'emergency' | 'telehealth';

export interface Appointment {
  id: string;
  patient: string;
  doctor: string;
  patient_name?: string;
  patient_mrn?: string;
  doctor_name?: string;
  doctor_dept?: string;
  scheduled_at: string;
  end_time: string;
  duration_minutes: number;
  duration_display: string;
  appointment_type: AppointmentType;
  status: AppointmentStatus;
  status_display: string;
  priority: 1 | 2 | 3 | 4;
  chief_complaint?: string;
  notes?: string;
  cancellation_reason?: string;
  allowed_transitions: AppointmentStatus[];
  created_at: string;
}

export interface AppointmentCalendar {
  id: string;
  patient_name: string;
  doctor_name: string;
  scheduled_at: string;
  end_time: string;
  duration_minutes: number;
  appointment_type: AppointmentType;
  status: AppointmentStatus;
  priority: number;
  color_code: string;
}

// ─── Billing ──────────────────────────────────────────────────────────────────
export type InvoiceStatus =
  | 'draft' | 'issued' | 'partially_paid' | 'paid' | 'voided' | 'overdue';

export interface InvoiceItem {
  id: string;
  description: string;
  item_type: string;
  unit_price: string;
  quantity: number;
  line_total: string;
  reference_id?: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  patient: string;
  patient_name: string;
  patient_mrn?: string;
  status: InvoiceStatus;
  status_display: string;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  discount_amount: string;
  total_amount: string;
  amount_paid: string;
  balance_due: string;
  currency: string;
  is_overdue: boolean;
  is_fully_paid: boolean;
  is_editable: boolean;
  notes?: string;
  items: InvoiceItem[];
  issued_at?: string;
  due_at?: string;
  paid_at?: string;
  created_at: string;
}

// ─── Pharmacy ─────────────────────────────────────────────────────────────────
export interface Drug {
  id: string;
  name: string;
  generic_name: string;
  category: string;
  category_display: string;
  unit: string;
  strength?: string;
  stock_quantity: number;
  reorder_level: number;
  unit_price: string;
  is_low_stock: boolean;
  is_out_of_stock: boolean;
  is_expired: boolean;
  days_until_expiry?: number;
  requires_prescription: boolean;
  controlled_drug: boolean;
  expiry_date?: string;
  is_active: boolean;
}

export type PrescriptionStatus = 'pending' | 'dispensed' | 'cancelled' | 'expired';

export interface Prescription {
  id: string;
  patient: string;
  patient_name: string;
  patient_mrn: string;
  doctor: string;
  doctor_name: string;
  drug: string;
  drug_name: string;
  drug_strength?: string;
  dosage: string;
  frequency: string;
  duration_days: number;
  quantity_prescribed: number;
  instructions?: string;
  route?: string;
  status: PrescriptionStatus;
  status_display: string;
  is_pending: boolean;
  prescribed_at: string;
  dispensed_at?: string;
  expiry_date?: string;
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
export interface DashboardStats {
  todayAppointments: number;
  activePatients: number;
  pendingPrescriptions: number;
  outstandingInvoices: number;
  lowStockDrugs: number;
  availableDoctors: number;
}
