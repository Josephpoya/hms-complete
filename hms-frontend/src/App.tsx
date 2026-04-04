/**
 * App.tsx — root routing tree.
 * All authenticated routes share AppLayout.
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider }      from './auth/AuthContext';
import { ProtectedRoute }    from './auth/ProtectedRoute';
import { AppLayout }         from './components/layout/AppLayout';

// Pages
import { LoginPage }         from './pages/login/LoginPage';
import { DashboardPage }     from './pages/dashboard/DashboardPage';
import { PatientsPage }      from './pages/patients/PatientsPage';
import { PatientDetailPage } from './pages/patients/PatientDetailPage';
import { NewPatientPage }    from './pages/patients/NewPatientPage';
import { EditPatientPage }   from './pages/patients/EditPatientPage';
import { AppointmentsPage }  from './pages/appointments/AppointmentsPage';
import { BillingPage }       from './pages/billing/BillingPage';
import { InvoiceCreatePage } from './pages/billing/InvoiceCreatePage';
import { PharmacyPage }      from './pages/pharmacy/PharmacyPage';

function Shell({ children, roles }: { children: React.ReactNode; roles?: string[] }) {
  return (
    <ProtectedRoute allowedRoles={roles as any}>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  );
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-7xl font-black text-slate-100 mb-2">404</p>
      <h1 className="text-xl font-bold text-slate-700 mb-1">Page not found</h1>
      <p className="text-sm text-slate-400 mb-6">The page you're looking for doesn't exist.</p>
      <a href="/dashboard" className="text-sm text-blue-600 hover:text-blue-700 font-medium">
        ← Dashboard
      </a>
    </div>
  );
}

function Unauthorized() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-7xl font-black text-slate-100 mb-2">403</p>
      <h1 className="text-xl font-bold text-slate-700 mb-1">Access denied</h1>
      <p className="text-sm text-slate-400 mb-6">You don't have permission to view this page.</p>
      <a href="/dashboard" className="text-sm text-blue-600 hover:text-blue-700 font-medium">
        ← Dashboard
      </a>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public */}
          <Route path="/login"        element={<LoginPage />} />
          <Route path="/unauthorized" element={<Unauthorized />} />
          <Route path="/"             element={<Navigate to="/dashboard" replace />} />

          {/* All roles */}
          <Route path="/dashboard"          element={<Shell><DashboardPage /></Shell>} />
          <Route path="/patients"           element={<Shell><PatientsPage /></Shell>} />
          <Route path="/patients/new"       element={<Shell roles={['admin','receptionist']}><NewPatientPage /></Shell>} />
          <Route path="/patients/:id"       element={<Shell><PatientDetailPage /></Shell>} />
          <Route path="/patients/:id/edit"  element={<Shell roles={['admin','receptionist']}><EditPatientPage /></Shell>} />
          <Route path="/appointments"       element={<Shell><AppointmentsPage /></Shell>} />

          {/* Role-restricted */}
          <Route path="/billing"            element={<Shell roles={['admin','receptionist']}><BillingPage /></Shell>} />
          <Route path="/billing/new"        element={<Shell roles={['admin','receptionist']}><InvoiceCreatePage /></Shell>} />
          <Route path="/pharmacy"           element={<Shell roles={['admin','doctor','nurse']}><PharmacyPage /></Shell>} />

          {/* Catch-all */}
          <Route path="*" element={<Shell><NotFound /></Shell>} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
