# HMS Frontend — React + TypeScript + Tailwind

## Stack
- **React 18** + **TypeScript** — strict mode
- **Vite** — build tool and dev server
- **React Router v6** — client-side routing with protected routes
- **Axios** — HTTP client with JWT auto-refresh
- **Tailwind CSS** — utility-first styling
- **lucide-react** — icon library
- **date-fns** — date formatting

## Structure

```
src/
├── auth/
│   ├── AuthContext.tsx     # JWT state, permission matrix, login/logout
│   └── ProtectedRoute.tsx  # Route guard with role-based redirects
├── services/
│   ├── api.ts              # Axios instance, token refresh, error normalisation
│   ├── authService.ts      # Login, logout, JWT decode
│   ├── patientService.ts   # Patient CRUD + search + export
│   ├── appointmentService.ts
│   ├── billingService.ts
│   └── pharmacyService.ts
├── components/
│   ├── ui/index.tsx        # Button, Input, Card, Table, Modal, Badge, etc.
│   └── layout/AppLayout.tsx # Sidebar + topbar shell
├── pages/
│   ├── login/LoginPage.tsx
│   ├── dashboard/DashboardPage.tsx
│   ├── patients/PatientsPage.tsx
│   ├── appointments/AppointmentsPage.tsx
│   ├── billing/BillingPage.tsx
│   └── pharmacy/PharmacyPage.tsx
└── types/index.ts          # All TypeScript interfaces
```

## Quickstart

```bash
cp .env.example .env
npm install
npm run dev
```

App runs on http://localhost:3000.
Backend must be running on http://localhost:8000.

## Auth flow

1. `LoginPage` submits email + password to `POST /api/v1/auth/login/`
2. JWT pair stored in **sessionStorage** (cleared when tab closes — safer for PHI)
3. `AuthProvider` decodes the access token to extract `role`, `email`, `user_id`
4. All Axios requests inject `Authorization: Bearer <token>` via interceptor
5. On 401 response, interceptor silently refreshes the token once
6. On refresh failure, user is redirected to `/login`

## Role-based access

Permissions are defined in `AuthContext.tsx`:

| Permission | Admin | Doctor | Nurse | Receptionist |
|---|:---:|:---:|:---:|:---:|
| `patients:read` | ✓ | ✓ | ✓ | ✓ |
| `patients:write` | ✓ | | | ✓ |
| `patients:delete` | ✓ | | | |
| `records:write` | ✓ | ✓ | ✓ | |
| `appointments:write` | ✓ | | | ✓ |
| `appointments:status` | ✓ | ✓ | ✓ | |
| `billing:write` | ✓ | | | ✓ |
| `pharmacy:dispense` | ✓ | | ✓ | |
| `prescriptions:write` | ✓ | ✓ | | |
| `users:manage` | ✓ | | | |

Usage in components:
```tsx
const { can, isRole } = useAuth();

{can('patients:write') && <Button>New patient</Button>}
{isRole('admin', 'doctor') && <AdminPanel />}
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000/api/v1` | Django backend URL |

## Build

```bash
npm run build        # outputs to dist/
npm run preview      # preview production build locally
```
