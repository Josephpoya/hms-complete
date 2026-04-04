/**
 * PatientsPage — list with DataTable, search, filters, CRUD actions.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { patientService } from '../../services/patientService';
import { usePaginatedQuery, useMutation, useDebounce } from '../../hooks/useApi';
import { toast } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { Patient } from '../../types';
import { DataTable, Column } from '../../components/ui/DataTable';
import {
  Card, Button, Badge, Alert, Pagination, EmptyState,
} from '../../components/ui';
import { FilterBar }    from '../../components/shared/FilterBar';
import { PageHeader }   from '../../components/shared/PageHeader';
import { ConfirmDialog } from '../../components/shared/ConfirmDialog';
import { Plus, Eye, Edit2, Trash2, Download, Users, Phone } from 'lucide-react';
import { fmt } from '../../utils/formatters';
import { clsx } from 'clsx';

const GENDER_VARIANT: Record<string, any> = {
  male: 'blue', female: 'purple', other: 'gray', prefer_not_to_say: 'gray',
};
const BLOOD_COLOR: Record<string, string> = {
  'O+':'text-red-700 bg-red-50','O-':'text-red-800 bg-red-100',
  'A+':'text-blue-700 bg-blue-50','A-':'text-blue-800 bg-blue-100',
  'B+':'text-green-700 bg-green-50','B-':'text-green-800 bg-green-100',
  'AB+':'text-purple-700 bg-purple-50','AB-':'text-purple-800 bg-purple-100',
};

export function PatientsPage() {
  const { can } = useAuth();
  const navigate = useNavigate();

  const [search,  setSearch]  = useState('');
  const [genderF, setGenderF] = useState('');
  const [bloodF,  setBloodF]  = useState('');
  const [deleteModal, setDeleteModal] = useState<Patient | null>(null);

  const dSearch = useDebounce(search);

  const { data, loading, error, page, setPage, refetch } = usePaginatedQuery(
    (p) => patientService.list({
      search:     dSearch || undefined,
      gender:     genderF || undefined,
      blood_type: bloodF  || undefined,
      page:       p,
      page_size:  25,
      ordering:   'last_name',
    }),
    [dSearch, genderF, bloodF],
  );

  const deactivate = useMutation(
    (id: string) => patientService.deactivate(id, 'Deactivated via admin panel'),
    {
      onSuccess: () => {
        toast('Patient deactivated.', 'success');
        setDeleteModal(null);
        refetch();
      },
    },
  );

  async function handleExport() {
    try {
      const blob = await patientService.export();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = `patients-${new Date().toISOString().slice(0,10)}.csv`;
      a.click(); URL.revokeObjectURL(url);
      toast('Export downloaded.', 'success');
    } catch (e: any) { toast(e?.message ?? 'Export failed.', 'error'); }
  }

  const columns: Column<Patient>[] = [
    {
      key: 'name', header: 'Patient', sortable: true,
      render: p => (
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-bold text-blue-700">
              {p.first_name.charAt(0)}{p.last_name.charAt(0)}
            </span>
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900">{p.full_name}</p>
            <p className="text-xs text-slate-400">Age {p.age}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'mrn', header: 'MRN', width: '120px',
      render: p => (
        <span className="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded text-slate-600">
          {p.mrn}
        </span>
      ),
    },
    {
      key: 'contact', header: 'Contact',
      render: p => (
        <div>
          <p className="text-sm flex items-center gap-1.5">
            <Phone size={11} className="text-slate-400" /> {p.phone}
          </p>
          {p.email && <p className="text-xs text-slate-400 truncate max-w-40">{p.email}</p>}
        </div>
      ),
    },
    {
      key: 'gender', header: 'Gender', width: '90px',
      render: p => <Badge variant={GENDER_VARIANT[p.gender]}>{p.gender}</Badge>,
    },
    {
      key: 'blood_type', header: 'Blood', width: '70px',
      render: p => p.blood_type ? (
        <span className={clsx('text-xs font-bold px-2 py-0.5 rounded', BLOOD_COLOR[p.blood_type] ?? 'bg-gray-100 text-gray-700')}>
          {p.blood_type}
        </span>
      ) : <span className="text-slate-300 text-xs">—</span>,
    },
    {
      key: 'flags', header: 'Flags',
      render: p => (
        <div className="flex flex-wrap gap-1">
          {p.is_diabetic      && <Badge variant="amber">DM</Badge>}
          {p.is_hypertensive  && <Badge variant="red">HTN</Badge>}
          {p.allergies    && <Badge variant="purple">Allergy</Badge>}
        </div>
      ),
    },
    {
      key: 'insurance', header: 'Insurance', width: '100px',
      render: p => p.insurance_provider ? (
        <Badge variant={p.insurance_is_valid ? 'green' : 'red'}>
          {p.insurance_is_valid ? 'Valid' : 'Expired'}
        </Badge>
      ) : <span className="text-slate-300 text-xs">—</span>,
    },
    {
      key: 'balance', header: 'Balance', align: 'right', width: '120px',
      render: p => parseFloat(p.outstanding_balance) > 0 ? (
        <span className="text-red-600 font-semibold text-sm">
          {fmt.currency(p.outstanding_balance)}
        </span>
      ) : <span className="text-green-600 text-xs">Clear</span>,
    },
    {
      key: 'actions', header: '', width: '90px', align: 'right',
      render: p => (
        <div className="flex items-center justify-end gap-1" onClick={e => e.stopPropagation()}>
          {can('patients:write') && (
            <button onClick={() => navigate(`/patients/${p.id}/edit`)}
              className="p-1.5 rounded text-slate-300 hover:text-amber-600 hover:bg-amber-50 transition-colors" title="Edit">
              <Edit2 size={13} />
            </button>
          )}
          {can('patients:delete') && (
            <button onClick={() => setDeleteModal(p)}
              className="p-1.5 rounded text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors" title="Deactivate">
              <Trash2 size={13} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="max-w-[1400px] mx-auto space-y-5">
      <PageHeader
        title="Patients"
        subtitle={data ? `${data.count.toLocaleString()} registered` : undefined}
        actions={
          <div className="flex items-center gap-2">
            {can('patients:delete') && (
              <Button variant="secondary" size="sm" onClick={handleExport}>
                <Download size={14} /> Export
              </Button>
            )}
            {can('patients:write') && (
              <Button size="sm" onClick={() => navigate('/patients/new')}>
                <Plus size={14} /> New patient
              </Button>
            )}
          </div>
        }
      />

      {(error || deactivate.error) && (
        <Alert variant="error">{error || deactivate.error}</Alert>
      )}

      {/* Filters */}
      <FilterBar search={search} onSearch={setSearch} searchPlaceholder="Name, MRN, phone, email…">
        <select value={genderF} onChange={e => setGenderF(e.target.value)}
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-200 bg-white">
          <option value="">All genders</option>
          <option value="male">Male</option>
          <option value="female">Female</option>
          <option value="other">Other</option>
        </select>
        <select value={bloodF} onChange={e => setBloodF(e.target.value)}
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-200 bg-white">
          <option value="">All blood types</option>
          {['A+','A-','B+','B-','AB+','AB-','O+','O-'].map(b => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
      </FilterBar>

      {/* Table */}
      <Card>
        <DataTable
          columns={columns}
          data={data?.results ?? []}
          loading={loading}
          rowKey={p => p.id}
          onRowClick={p => navigate(`/patients/${p.id}`)}
          emptyNode={
            <div className="py-16 text-center">
              <Users size={40} className="mx-auto text-slate-200 mb-3" />
              <p className="font-medium text-slate-500 mb-1">No patients found</p>
              <p className="text-sm text-slate-400 mb-5">
                {search ? `No results for "${search}".` : 'No patients registered yet.'}
              </p>
              {can('patients:write') && !search && (
                <Button size="sm" onClick={() => navigate('/patients/new')}>
                  <Plus size={13} /> Register first patient
                </Button>
              )}
            </div>
          }
        />
        {data && <Pagination page={page} total={data.count} pageSize={25} onChange={setPage} />}
      </Card>

      {/* Deactivate confirmation */}
      <ConfirmDialog
        isOpen={!!deleteModal}
        onClose={() => setDeleteModal(null)}
        onConfirm={() => deactivate.mutate(deleteModal!.id)}
        title={`Deactivate ${deleteModal?.full_name}`}
        message={
          <>
            This will soft-deactivate <strong>{deleteModal?.full_name}</strong> (MRN: {deleteModal?.mrn}).
            The record is retained for medical-legal compliance and can be reactivated by an administrator.
          </>
        }
        variant="danger"
        confirmLabel="Deactivate patient"
        loading={deactivate.loading}
      />
    </div>
  );
}
