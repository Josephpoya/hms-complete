import React, { useState, useEffect, useCallback } from 'react';
import { pharmacyService } from '../../services/pharmacyService';
import { useAuth } from '../../auth/AuthContext';
import { Drug, Prescription, PaginatedResponse } from '../../types';
import {
  Card, CardHeader, CardContent, Table, Th, Td, Pagination,
  Button, Badge, StatusBadge, Alert, Spinner, EmptyState, Modal,
} from '../../components/ui';
import { Pill, Search, AlertTriangle, Package, ClipboardList, CheckCircle2, XCircle } from 'lucide-react';
import { clsx } from 'clsx';
import { format, parseISO } from 'date-fns';

type Tab = 'drugs' | 'prescriptions';

export function PharmacyPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>('drugs');
  const [drugs, setDrugs]   = useState<PaginatedResponse<Drug> | null>(null);
  const [rxs,   setRxs]     = useState<PaginatedResponse<Prescription> | null>(null);
  const [loading, setLoading] = useState(true);
  const [page,    setPage]    = useState(1);
  const [search,  setSearch]  = useState('');
  const [error,   setError]   = useState('');
  const [dispenseModal, setDispenseModal] = useState<Prescription | null>(null);
  const [cancelModal,   setCancelModal]   = useState<Prescription | null>(null);
  const [cancelReason,  setCancelReason]  = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const loadDrugs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await pharmacyService.drugs.list({ search: search || undefined, page });
      setDrugs(r);
    } catch (e: any) { setError(e?.message ?? 'Failed to load drugs.');
    } finally { setLoading(false); }
  }, [search, page]);

  const loadRxs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await pharmacyService.prescriptions.list({ search: search || undefined, page, status: 'pending' });
      setRxs(r);
    } catch (e: any) { setError(e?.message ?? 'Failed to load prescriptions.');
    } finally { setLoading(false); }
  }, [search, page]);

  useEffect(() => { tab === 'drugs' ? loadDrugs() : loadRxs(); }, [tab, loadDrugs, loadRxs]);

  async function handleDispense() {
    if (!dispenseModal) return;
    setActionLoading(true);
    try {
      await pharmacyService.prescriptions.dispense(dispenseModal.id);
      setDispenseModal(null); tab === 'prescriptions' ? loadRxs() : loadDrugs();
    } catch (e: any) { setError(e?.message ?? 'Dispense failed.');
    } finally { setActionLoading(false); }
  }

  async function handleCancel() {
    if (!cancelModal || !cancelReason) return;
    setActionLoading(true);
    try {
      await pharmacyService.prescriptions.cancel(cancelModal.id, cancelReason);
      setCancelModal(null); setCancelReason(''); loadRxs();
    } catch (e: any) { setError(e?.message ?? 'Cancel failed.');
    } finally { setActionLoading(false); }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pharmacy</h1>
          <p className="text-sm text-slate-500 mt-0.5">Drug catalogue and prescriptions</p>
        </div>
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        {([['drugs','Drug catalogue', <Package size={14}/>], ['prescriptions','Prescriptions', <ClipboardList size={14}/>]] as const).map(([t, label, icon]) => (
          <button key={t} onClick={() => { setTab(t as Tab); setPage(1); setSearch(''); }}
            className={clsx('flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
              tab === t ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900')}>
            {icon}{label}
          </button>
        ))}
      </div>

      {/* Search */}
      <Card>
        <CardContent className="py-3">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input type="search"
              placeholder={tab === 'drugs' ? 'Search drug name, barcode…' : 'Search patient, drug name…'}
              value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
          </div>
        </CardContent>
      </Card>

      {/* Drug table */}
      {tab === 'drugs' && (
        <Card>
          {loading ? (
            <div className="flex justify-center py-16"><Spinner size="lg" /></div>
          ) : !drugs?.results.length ? (
            <EmptyState icon={<Pill size={40} />} title="No drugs found" />
          ) : (
            <>
              <Table>
                <thead>
                  <tr>
                    <Th>Drug</Th>
                    <Th>Category</Th>
                    <Th>Stock</Th>
                    <Th>Reorder at</Th>
                    <Th>Unit price</Th>
                    <Th>Expiry</Th>
                    <Th>Flags</Th>
                  </tr>
                </thead>
                <tbody>
                  {drugs.results.map(d => (
                    <tr key={d.id} className={clsx('hover:bg-slate-50', (d.is_low_stock || d.is_expired) && 'bg-amber-50/30')}>
                      <Td>
                        <div>
                          <p className="font-medium text-slate-900">{d.name}</p>
                          <p className="text-xs text-slate-500">{d.generic_name}{d.strength && ` · ${d.strength}`}</p>
                        </div>
                      </Td>
                      <Td><Badge variant="gray">{d.category_display}</Badge></Td>
                      <Td>
                        <span className={clsx('font-bold', d.stock_quantity === 0 ? 'text-red-600' : d.is_low_stock ? 'text-amber-600' : 'text-slate-900')}>
                          {d.stock_quantity} {d.unit}s
                        </span>
                      </Td>
                      <Td><span className="text-slate-500">{d.reorder_level}</span></Td>
                      <Td>UGX {parseFloat(d.unit_price).toLocaleString()}</Td>
                      <Td>
                        {d.expiry_date ? (
                          <span className={clsx('text-xs', d.is_expired ? 'text-red-600 font-medium' : d.days_until_expiry! < 30 ? 'text-amber-600' : 'text-slate-600')}>
                            {format(parseISO(d.expiry_date), 'dd MMM yyyy')}
                            {d.days_until_expiry != null && d.days_until_expiry >= 0 && (
                              <span className="block text-slate-400">{d.days_until_expiry}d left</span>
                            )}
                          </span>
                        ) : '—'}
                      </Td>
                      <Td>
                        <div className="flex flex-col gap-0.5">
                          {d.is_low_stock     && <Badge variant="amber">Low stock</Badge>}
                          {d.is_expired       && <Badge variant="red">Expired</Badge>}
                          {d.controlled_drug  && <Badge variant="purple">Controlled</Badge>}
                          {!d.requires_prescription && <Badge variant="gray">OTC</Badge>}
                        </div>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <Pagination page={page} total={drugs.count} pageSize={20} onChange={setPage} />
            </>
          )}
        </Card>
      )}

      {/* Prescriptions table */}
      {tab === 'prescriptions' && (
        <Card>
          {loading ? (
            <div className="flex justify-center py-16"><Spinner size="lg" /></div>
          ) : !rxs?.results.length ? (
            <EmptyState icon={<ClipboardList size={40} />} title="No pending prescriptions" description="All prescriptions have been dispensed or cancelled." />
          ) : (
            <>
              <Table>
                <thead>
                  <tr>
                    <Th>Patient</Th>
                    <Th>Drug</Th>
                    <Th>Dosage</Th>
                    <Th>Doctor</Th>
                    <Th>Status</Th>
                    <Th>Prescribed</Th>
                    <Th>Expires</Th>
                    {can('pharmacy:dispense') && <Th>Actions</Th>}
                  </tr>
                </thead>
                <tbody>
                  {rxs.results.map(rx => (
                    <tr key={rx.id} className="hover:bg-slate-50">
                      <Td>
                        <p className="font-medium text-slate-900">{rx.patient_name}</p>
                        <p className="text-xs font-mono text-slate-400">{rx.patient_mrn}</p>
                      </Td>
                      <Td>
                        <p className="font-medium text-slate-900">{rx.drug_name}</p>
                        {rx.drug_strength && <p className="text-xs text-slate-500">{rx.drug_strength}</p>}
                      </Td>
                      <Td>
                        <p className="text-sm">{rx.dosage} · {rx.frequency}</p>
                        <p className="text-xs text-slate-500">{rx.duration_days}d · qty {rx.quantity_prescribed}</p>
                      </Td>
                      <Td><span className="text-sm">{rx.doctor_name}</span></Td>
                      <Td><StatusBadge status={rx.status} /></Td>
                      <Td><span className="text-xs">{format(parseISO(rx.prescribed_at), 'dd MMM yyyy')}</span></Td>
                      <Td>
                        {rx.expiry_date ? (
                          <span className="text-xs">{format(parseISO(rx.expiry_date), 'dd MMM yyyy')}</span>
                        ) : '—'}
                      </Td>
                      {can('pharmacy:dispense') && (
                        <Td>
                          {rx.is_pending && (
                            <div className="flex items-center gap-1.5">
                              <Button size="sm" onClick={() => setDispenseModal(rx)}>
                                <CheckCircle2 size={12} /> Dispense
                              </Button>
                              <Button size="sm" variant="danger" onClick={() => setCancelModal(rx)}>
                                <XCircle size={12} /> Cancel
                              </Button>
                            </div>
                          )}
                        </Td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </Table>
              <Pagination page={page} total={rxs.count} pageSize={20} onChange={setPage} />
            </>
          )}
        </Card>
      )}

      {/* Dispense confirmation */}
      <Modal isOpen={!!dispenseModal} onClose={() => setDispenseModal(null)} title="Confirm dispense" size="sm">
        {dispenseModal && (
          <div className="space-y-3">
            <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
              <div className="flex justify-between"><span className="text-slate-500">Patient</span><strong>{dispenseModal.patient_name}</strong></div>
              <div className="flex justify-between"><span className="text-slate-500">Drug</span><strong>{dispenseModal.drug_name}</strong></div>
              <div className="flex justify-between"><span className="text-slate-500">Dosage</span><span>{dispenseModal.dosage} · {dispenseModal.frequency}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Qty</span><strong>{dispenseModal.quantity_prescribed} units</strong></div>
            </div>
            <Alert variant="info">Stock will be deducted atomically. This action cannot be undone.</Alert>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDispenseModal(null)}>Cancel</Button>
              <Button onClick={handleDispense} isLoading={actionLoading}>Confirm dispense</Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Cancel prescription modal */}
      <Modal isOpen={!!cancelModal} onClose={() => setCancelModal(null)} title="Cancel prescription" size="sm">
        <div className="space-y-3">
          <Alert variant="warning">Cancelling will mark this prescription as cancelled. Please provide a reason.</Alert>
          <textarea value={cancelReason} onChange={e => setCancelReason(e.target.value)}
            placeholder="Reason for cancellation…" rows={3}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none resize-none" />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => { setCancelModal(null); setCancelReason(''); }}>Back</Button>
            <Button variant="danger" onClick={handleCancel} isLoading={actionLoading} disabled={!cancelReason}>Cancel prescription</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
