# HMS REST API — Endpoint Reference

Base URL: `https://yourdomain.com/api/v1/`  
Authentication: `Authorization: Bearer <access_token>`  
Content-Type: `application/json`

---

## Auth  `/api/v1/auth/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| POST | `/auth/login/` | Obtain JWT pair | Public (throttled 5/min) |
| POST | `/auth/refresh/` | Refresh access token | Public |
| POST | `/auth/logout/` | Blacklist refresh token | Authenticated |
| GET | `/auth/me/` | Current user profile | Authenticated |
| PATCH | `/auth/me/` | Update own profile | Authenticated |
| POST | `/auth/me/password/` | Change own password | Authenticated |
| GET | `/auth/users/` | List all users | Admin |
| POST | `/auth/users/` | Create user | Admin |
| GET | `/auth/users/<id>/` | Get user | Admin / Self |
| PATCH | `/auth/users/<id>/` | Update user | Admin |
| DELETE | `/auth/users/<id>/` | Deactivate user | Admin |
| POST | `/auth/users/<id>/unlock/` | Clear lockout | Admin |
| GET | `/auth/users/roles/` | List role choices | Admin |

---

## Patients  `/api/v1/patients/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| GET | `/patients/` | List active patients (paginated) | All staff |
| POST | `/patients/` | Register new patient | Admin, Receptionist |
| GET | `/patients/<id>/` | Retrieve patient detail | All staff |
| PATCH | `/patients/<id>/` | Update patient | Admin, Receptionist |
| DELETE | `/patients/<id>/` | Soft-deactivate patient | Admin |
| GET | `/patients/<id>/history/` | Patient's EHR history | Clinical staff |
| GET | `/patients/search/?q=<term>` | Quick autocomplete search | All staff |
| GET | `/patients/export/` | CSV export | Admin |

**Query params:** `?gender=male&blood_type=O%2B&search=Okello&ordering=-created_at&page=2&page_size=25`

---

## Doctors  `/api/v1/doctors/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| GET | `/doctors/` | List doctors | All staff |
| POST | `/doctors/` | Create doctor profile | Admin |
| GET | `/doctors/<id>/` | Retrieve doctor | All staff |
| PATCH | `/doctors/<id>/` | Update doctor | Admin |
| DELETE | `/doctors/<id>/` | Deactivate doctor | Admin |
| GET | `/doctors/workload/` | Today's patient counts | All staff |
| GET | `/doctors/available/` | Available doctors only | All staff |
| GET | `/doctors/<id>/availability/` | List weekly slots | All staff |
| POST | `/doctors/<id>/availability/` | Add slot | Admin |
| PATCH | `/doctors/<id>/availability/<id>/` | Update slot | Admin |
| DELETE | `/doctors/<id>/availability/<id>/` | Remove slot | Admin |

---

## Appointments  `/api/v1/appointments/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| GET | `/appointments/` | List appointments | All staff |
| POST | `/appointments/` | Book appointment | Admin, Receptionist |
| GET | `/appointments/<id>/` | Retrieve appointment | All staff |
| PATCH | `/appointments/<id>/` | Reschedule | Admin, Receptionist |
| DELETE | `/appointments/<id>/` | Cancel (soft) | Admin, Receptionist |
| PATCH | `/appointments/<id>/status/` | State machine transition | Clinical staff |
| GET | `/appointments/calendar/` | Calendar view | All staff |
| GET | `/appointments/today/` | Today's appointments | All staff |

**Status transitions:**  
`booked → checked_in → in_progress → completed`  
`booked → cancelled`  
`checked_in → no_show`

**Query params:** `?status=booked&doctor=<uuid>&scheduled_at__date=2024-01-15`

---

## Billing  `/api/v1/billing/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| GET | `/billing/invoices/` | List invoices | All staff |
| POST | `/billing/invoices/` | Create invoice | Admin, Receptionist |
| GET | `/billing/invoices/<id>/` | Retrieve invoice | All staff |
| PATCH | `/billing/invoices/<id>/` | Update draft invoice | Admin, Receptionist |
| DELETE | `/billing/invoices/<id>/` | Void or delete | Admin |
| POST | `/billing/invoices/<id>/action/` | issue / mark_overdue / void | Admin, Receptionist |
| POST | `/billing/invoices/<id>/payment/` | Record payment | Admin, Receptionist |
| GET | `/billing/invoices/<id>/items/` | List line items | All staff |
| POST | `/billing/invoices/<id>/items/` | Add line item | Admin, Receptionist |
| PATCH | `/billing/invoices/<id>/items/<id>/` | Update item | Admin, Receptionist |
| DELETE | `/billing/invoices/<id>/items/<id>/` | Remove item | Admin, Receptionist |

---

## Pharmacy  `/api/v1/pharmacy/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| GET | `/pharmacy/drugs/` | Drug catalogue | All staff |
| POST | `/pharmacy/drugs/` | Add drug | Admin |
| GET | `/pharmacy/drugs/<id>/` | Drug detail | All staff |
| PATCH | `/pharmacy/drugs/<id>/` | Update drug | Admin |
| DELETE | `/pharmacy/drugs/<id>/` | Deactivate | Admin |
| POST | `/pharmacy/drugs/<id>/restock/` | Add stock | Admin |
| GET | `/pharmacy/drugs/low-stock/` | Below reorder level | All staff |
| GET | `/pharmacy/drugs/expiring/?days=30` | Expiring soon | All staff |
| GET | `/pharmacy/prescriptions/` | List prescriptions | Clinical staff |
| POST | `/pharmacy/prescriptions/` | Issue prescription | Doctor |
| GET | `/pharmacy/prescriptions/<id>/` | Prescription detail | Clinical staff |
| POST | `/pharmacy/prescriptions/<id>/dispense/` | Dispense medication | Admin, Nurse |
| POST | `/pharmacy/prescriptions/<id>/cancel/` | Cancel prescription | Clinical staff |

---

## Records  `/api/v1/records/`

| Method | URL | Description | Roles |
|--------|-----|-------------|-------|
| GET | `/records/` | List EHR records | Clinical staff |
| POST | `/records/` | Create EHR note | Doctor |
| GET | `/records/<id>/` | Retrieve full record | Clinical staff |
| PATCH | `/records/<id>/` | Update (within 24h window) | Doctor (own records) |
| POST | `/records/<id>/attachments/` | Upload file (multipart) | Clinical staff |
| DELETE | `/records/<id>/attachments/<key>/` | Remove attachment | Clinical staff |
| POST | `/records/<id>/lock/` | Manually lock | Admin |
| GET | `/records/patient/<patient_id>/` | All records for patient | Clinical staff |
| GET | `/records/audit/` | Audit log | Admin |
| GET | `/records/audit/<id>/` | Single audit event | Admin |

---

## Response format

**Success (list):**
```json
{
  "count": 150,
  "next": "https://domain.com/api/v1/patients/?page=2",
  "previous": null,
  "results": [...]
}
```

**Error (all):**
```json
{
  "error": {
    "status_code": 400,
    "detail": { "scheduled_at": ["Appointment must be in the future."] }
  }
}
```

**Auth error:**
```json
{ "error": { "status_code": 401, "detail": "Authentication credentials were not provided." } }
```
