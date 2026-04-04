/**
 * BillingPage — invoice list with search, status filter, payment modal.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { billingService } from '../../services/billingService';
import { usePaginatedQuery, useMutation, useDebounce } from '../../hooks/useApi';
import { toast } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { Invoice } from '../../types';
import { DataTable, Column } from '../../components/ui/DataTable';
import {
  Card, CardHeader, CardContent, Button,
  Badge, StatusBadge, Alert, Modal, Pagination,
} from '../../components/ui';
import { FilterBar }   from '../../components/shared/FilterBar';
import { PageHeader }  from '../../components/shared/PageHeader';
import { ConfirmDialog } from '../../components/shared/ConfirmDialog';
import {
  Plus, DollarSign, FileText, TrendingUp, AlertCircle,
  Eye, Send, XCircle, CheckCircle2,
} from 'lucide-react';
import { fmt } from '../../utils/formatters';
import { clsx } from 'clsx';

const STATUS_TABS = ['', 'draft', 'issued', 'partially_paid', 'overdue', 'paid', 'voided'];

export function BillingPage() {
  const { can } = useAuth();
  const navigate = useNavigate();

  const [search,  setSearch]  = useState('');
  const [statusF, setStatusF] = useState('');
  const [voidModal,  setVoidModal]  = useState<Invoice | null>(null);
  const [payModal,   setPayModal]   = useState<Invoice | null>(null);
  const [payForm, setPayForm] = useState({ amount: '', method: 'cash', notes: '' });

  const dSearch = useDebounce(search);

  const { data, loading, error, page, setPage, refetch } = usePaginatedQuery(
    (p) => billingService.list({ search: dSearch || undefined, status: statusF || undefined, page: p }),
    [dSearch, statusF],
  );

  const issueM = useMutation(
    (id: string) => billingService.action(id, 'issue'),
    { onSuccess: () => { toast('Invoice issued.', 'success'); refetch(); } },
  );

  const voidM = useMutation(
    (id: string) => billingService.action(id, 'void'),
    { onSuccess: () => { toast('Invoice voided.', 'success'); setVoidModal(null); refetch(); } },
  );

  const payM = useMutation(
    ({ id, amount, method, notes }: { id: string; amount: string; method: string; notes: string }) =>
      billingService.recordPayment(id, amount, method, notes),
    { onSuccess: () => { toast('Payment recorded.', 'success'); setPayModal(null); refetch(); } },
  );

  // Derived totals
  const outstanding = data?.results.reduce((s, inv) => s + parseFloat(inv.balance_due), 0) ?? 0;
  const overdue     = data?.results.filter(inv => inv.is_overdue).length ?? 0;

  const columns: Column<Invoice>[] = [
    {
      key: 'invoice_number', header: 'Invoice', width: '140px',
      render: inv => (
        <div>
          <p className="font-mono text-xs font-semibold text-slate-800">{inv.invoice_number}</p>
          <p className="text-xs text-slate-400">{fmt.date(inv.created_at)}</p>
        </div>
      ),
    },
    {
      key: 'patient', header: 'Patient',
      render: inv => (
        <div>
          <p className="text-sm font-medium text-slate-900">{inv.patient_name}</p>
          {inv.patient_mrn && <p className="text-xs font-mono text-slate-400">{inv.patient_mrn}</p>}
        </div>
      ),
    },
    {
      key: 'status', header: 'Status', width: '130px',
      render: inv => (
        <div className="flex flex-col gap-0.5">
          <StatusBadge status={inv.status} />
          {inv.is_overdue && <Badge variant="red">Overdue</Badge>}
        </div>
      ),
    },
    {
      key: 'total_amount', header: 'Total', align: 'right', width: '120px',
      render: inv => (
        <span className="font-semibold text-slate-800">
          {fmt.currency(inv.total_amount, inv.currency)}
        </span>
      ),
    },
    {
      key: 'amount_paid', header: 'Paid', align: 'right', width: '110px',
      render: inv => (
        <span className="text-green-600 font-medium">
          {parseFloat(inv.amount_paid) > 0 ? fmt.currency(inv.amount_paid, inv.currency) : '—'}
        </span>
      ),
    },
    {
      key: 'balance_due', header: 'Balance', align: 'right', width: '110px',
      render: inv => (
        <span className={clsx('font-bold', parseFloat(inv.balance_due) > 0 ? 'text-red-600' : 'text-green-600')}>
          {parseFloat(inv.balance_due) > 0
            ? fmt.currency(inv.balance_due, inv.currency)
            : <CheckCircle2 size={15} className="inline text-green-500" />}
        </span>
      ),
    },
    {
      key: 'due_at', header: 'Due', width: '100px',
      render: inv => inv.due_at ? (
        <span className={clsx('text-xs', inv.is_overdue && 'text-red-600 font-semibold')}>
          {fmt.date(inv.due_at)}
        </span>
      ) : <span className="text-slate-300">—</span>,
    },
    {
      key: 'actions', header: '', width: '140px', align: 'right',
      render: inv => (
        <div className="flex items-center justify-end gap-1">
          <button onClick={() => navigate(`/billing/${inv.id}`)}
            className="p-1.5 rounded text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors" title="View">
            <Eye size={14} />
          </button>

          {can('billing:write') && inv.status === 'draft' && (
            <button
              onClick={() => issueM.mutate(inv.id)}
              className="p-1.5 rounded text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors" title="Issue">
              <Send size={14} />
            </button>
          )}

          {can('billing:write') && ['issued', 'partially_paid', 'overdue'].includes(inv.status) && (
            <button
              onClick={() => { setPayModal(inv); setPayForm(f => ({ ...f, amount: inv.balance_due })); }}
              className="p-1.5 rounded text-slate-400 hover:text-green-600 hover:bg-green-50 transition-colors" title="Record payment">
              <DollarSign size={14} />
            </button>
          )}

          {can('billing:write') && !['paid', 'voided'].includes(inv.status) && (
            <button onClick={() => setVoidModal(inv)}
              className="p-1.5 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors" title="Void">
              <XCircle size={14} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Billing"
        subtitle={data ? `${data.count} invoices` : undefined}
        actions={
          can('billing:write') ? (
            <Button size="sm" onClick={() => navigate('/billing/new')}>
              <Plus size={14} /> New invoice
            </Button>
          ) : undefined
        }
      />

      {(error || issueM.error || voidM.error || payM.error) && (
        <Alert variant="error">{error || issueM.error || voidM.error || payM.error}</Alert>
      )}

      {/* Summary cards */}
      {data && (
        <div className="grid sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
            <div className="w-9 h-9 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
              <FileText size={18} className="text-purple-600" />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Total invoices</p>
              <p className="text-xl font-bold text-slate-900">{data.count}</p>
            </div>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
            <div className="w-9 h-9 bg-red-100 rounded-lg flex items-center justify-center flex-shrink-0">
              <TrendingUp size={18} className="text-red-600" />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Outstanding</p>
              <p className="text-xl font-bold text-red-700">{fmt.currency(outstanding)}</p>
            </div>
          </div>
          <div className={clsx(
            'bg-white rounded-xl border p-4 flex items-center gap-3',
            overdue > 0 ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-200',
          )}>
            <div className={clsx(
              'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
              overdue > 0 ? 'bg-amber-100' : 'bg-green-100',
            )}>
              <AlertCircle size={18} className={overdue > 0 ? 'text-amber-600' : 'text-green-600'} />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Overdue</p>
              <p className={clsx('text-xl font-bold', overdue > 0 ? 'text-amber-700' : 'text-green-700')}>
                {overdue}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <FilterBar search={search} onSearch={setSearch} searchPlaceholder="Invoice #, patient name or MRN…">
        <div className="flex flex-wrap gap-1">
          {STATUS_TABS.map(s => (
            <button key={s}
              onClick={() => { setStatusF(s); setPage(1); }}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize whitespace-nowrap',
                statusF === s ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}>
              {s === '' ? 'All' : s.replace('_', ' ')}
            </button>
          ))}
        </div>
      </FilterBar>

      {/* Table */}
      <Card>
        <DataTable
          columns={columns}
          data={data?.results ?? []}
          loading={loading}
          rowKey={inv => inv.id}
          onRowClick={inv => navigate(`/billing/${inv.id}`)}
          emptyNode={
            <div className="py-14 text-center">
              <FileText size={36} className="mx-auto text-slate-200 mb-3" />
              <p className="text-slate-500 font-medium">No invoices found</p>
              {can('billing:write') && (
                <Button size="sm" className="mt-4" onClick={() => navigate('/billing/new')}>
                  <Plus size={13} /> Create first invoice
                </Button>
              )}
            </div>
          }
        />
        {data && <Pagination page={page} total={data.count} pageSize={25} onChange={setPage} />}
      </Card>

      {/* Void confirmation */}
      <ConfirmDialog
        isOpen={!!voidModal}
        onClose={() => setVoidModal(null)}
        onConfirm={() => voidM.mutate(voidModal!.id)}
        title={`Void invoice ${voidModal?.invoice_number}`}
        message="This will mark the invoice as voided. This action cannot be undone."
        variant="danger"
        confirmLabel="Void invoice"
        loading={voidM.loading}
      />

      {/* Payment modal */}
      <Modal isOpen={!!payModal} onClose={() => setPayModal(null)}
        title={`Record payment — ${payModal?.invoice_number}`} size="sm">
        {payModal && (
          <div className="space-y-4">
            <div className="bg-slate-50 rounded-lg p-3.5 text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-500">Patient</span>
                <strong className="text-slate-800">{payModal.patient_name}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Invoice total</span>
                <strong>{fmt.currency(payModal.total_amount, payModal.currency)}</strong>
              </div>
              <div className="flex justify-between border-t border-slate-200 pt-2">
                <span className="text-slate-500">Balance due</span>
                <strong className="text-red-600">{fmt.currency(payModal.balance_due, payModal.currency)}</strong>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Amount ({payModal.currency})
              </label>
              <input
                type="number" step="0.01" min="0.01" max={payModal.balance_due}
                value={payForm.amount}
                onChange={e => setPayForm(f => ({ ...f, amount: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Payment method</label>
              <select
                value={payForm.method}
                onChange={e => setPayForm(f => ({ ...f, method: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none"
              >
                {[
                  ['cash','Cash'], ['mobile_money','Mobile Money'],
                  ['card','Card'], ['insurance','Insurance'], ['bank_transfer','Bank Transfer'],
                ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            <textarea
              value={payForm.notes}
              onChange={e => setPayForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Optional notes…"
              rows={2}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none resize-none"
            />

            {payM.error && <Alert variant="error">{payM.error}</Alert>}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" onClick={() => setPayModal(null)}>Cancel</Button>
              <Button
                isLoading={payM.loading}
                disabled={!payForm.amount || parseFloat(payForm.amount) <= 0}
                onClick={() => payM.mutate({ id: payModal.id, amount: payForm.amount, method: payForm.method, notes: payForm.notes })}
              >
                <DollarSign size={14} /> Record payment
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
