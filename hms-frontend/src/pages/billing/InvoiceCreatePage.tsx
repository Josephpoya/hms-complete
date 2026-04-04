/**
 * InvoiceCreatePage
 * ==================
 * Full invoice creation flow with:
 *  - Patient autocomplete
 *  - Live line items with running total
 *  - Tax rate and discount fields
 *  - Inline validation
 *  - Save as draft or issue immediately
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { billingService } from '../../services/billingService';
import { PatientAutocomplete } from '../../components/ui/PatientAutocomplete';
import { InvoiceLineItems, LineItem } from '../../components/ui/InvoiceLineItems';
import { Card, CardHeader, CardContent, Button, Alert, Input, Select } from '../../components/ui';
import { PageHeader } from '../../components/shared/PageHeader';
import { toast } from '../../hooks/useApi';
import { PatientMinimal } from '../../types';
import { ArrowLeft, Save, Send } from 'lucide-react';

interface FormState {
  patient:         string;
  appointment:     string;
  tax_rate:        string;
  discount_amount: string;
  currency:        string;
  notes:           string;
}

const EMPTY: FormState = {
  patient: '', appointment: '', tax_rate: '0',
  discount_amount: '0', currency: 'UGX', notes: '',
};

export function InvoiceCreatePage() {
  const navigate = useNavigate();
  const [form,    setForm]    = useState<FormState>(EMPTY);
  const [items,   setItems]   = useState<LineItem[]>([
    { description: '', item_type: 'consultation', unit_price: '', quantity: 1 },
  ]);
  const [selectedPatient, setSelectedPatient] = useState<PatientMinimal | null>(null);
  const [errors,  setErrors]  = useState<Record<string, string>>({});
  const [saving,  setSaving]  = useState<'draft' | 'issue' | null>(null);
  const [serverError, setServerError] = useState('');

  function setField(key: keyof FormState, value: string) {
    setForm(f => ({ ...f, [key]: value }));
    setErrors(e => ({ ...e, [key]: '' }));
  }

  // Running totals
  const subtotal = items.reduce((s, it) => s + (parseFloat(it.unit_price) || 0) * it.quantity, 0);
  const taxAmt   = subtotal * (parseFloat(form.tax_rate) || 0) / 100;
  const discount = parseFloat(form.discount_amount) || 0;
  const total    = subtotal + taxAmt - discount;

  function validateItems() {
    const errs: Record<number, Record<string, string>> = {};
    items.forEach((it, i) => {
      const e: Record<string, string> = {};
      if (!it.description.trim()) e.description = 'Required';
      if (!it.unit_price || parseFloat(it.unit_price) < 0) e.unit_price = 'Enter a price';
      if (Object.keys(e).length) errs[i] = e;
    });
    return errs;
  }

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!form.patient) e.patient = 'Please select a patient.';
    if (!items.length) e.items = 'Add at least one line item.';
    if (discount > subtotal) e.discount_amount = 'Discount cannot exceed subtotal.';
    setErrors(e);
    return Object.keys(e).length === 0 && Object.keys(validateItems()).length === 0;
  }

  async function handleSave(andIssue: boolean) {
    if (!validate()) return;
    const mode = andIssue ? 'issue' : 'draft';
    setSaving(mode);
    setServerError('');

    try {
      const invoice = await billingService.create({
        patient:         form.patient,
        tax_rate:        form.tax_rate        || '0',
        discount_amount: form.discount_amount || '0',
        currency:        form.currency,
        notes:           form.notes,
                items: (items.map(it => ({
          description: it.description,
          item_type:   it.item_type,
          unit_price:  it.unit_price,
          quantity:    it.quantity,
        })) as any),
      });

      if (andIssue) {
        await billingService.action(invoice.id, 'issue');
        toast(`Invoice ${invoice.invoice_number} issued.`, 'success');
      } else {
        toast(`Invoice ${invoice.invoice_number} saved as draft.`, 'success');
      }
      navigate('/billing');
    } catch (err: any) {
      if (err?.fields) {
        const fe: Record<string, string> = {};
        for (const [k, v] of Object.entries(err.fields)) {
          fe[k] = Array.isArray(v) ? v[0] : String(v);
        }
        setErrors(fe);
      } else {
        setServerError(err?.message ?? 'Failed to create invoice.');
      }
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <PageHeader
        title="New invoice"
        subtitle="Create and optionally issue immediately"
        backTo="/billing"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" isLoading={saving === 'draft'}
              disabled={!!saving} onClick={() => handleSave(false)}>
              <Save size={14} /> Save draft
            </Button>
            <Button isLoading={saving === 'issue'}
              disabled={!!saving} onClick={() => handleSave(true)}>
              <Send size={14} /> Issue invoice
            </Button>
          </div>
        }
      />

      {serverError && <Alert variant="error">{serverError}</Alert>}
      {errors.items && <Alert variant="warning">{errors.items}</Alert>}

      {/* Patient */}
      <Card>
        <CardHeader><h2 className="font-semibold text-slate-800">Patient</h2></CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <PatientAutocomplete
              value={form.patient}
              onChange={(id, p) => { setField('patient', id); setSelectedPatient(p ?? null); }}
              error={errors.patient}
            />
          </div>
          <Select label="Currency" id="currency" value={form.currency}
            onChange={e => setField('currency', e.target.value)}>
            <option value="UGX">UGX — Ugandan Shilling</option>
            <option value="USD">USD — US Dollar</option>
            <option value="KES">KES — Kenyan Shilling</option>
          </Select>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
            <input type="text" value={form.notes}
              onChange={e => setField('notes', e.target.value)}
              placeholder="Optional invoice notes…"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
          </div>
        </CardContent>
      </Card>

      {/* Line items */}
      <Card>
        <CardHeader><h2 className="font-semibold text-slate-800">Line items</h2></CardHeader>
        <CardContent>
          <InvoiceLineItems
            items={items}
            onChange={setItems}
            editable
            currency={form.currency}
          />
        </CardContent>
      </Card>

      {/* Totals */}
      <Card>
        <CardContent>
          <div className="flex flex-col sm:flex-row justify-end gap-6">
            {/* Tax + discount */}
            <div className="grid grid-cols-2 gap-3 w-full sm:w-64">
              <Input label="Tax rate (%)" id="tax_rate" type="number" min="0" max="100" step="0.5"
                value={form.tax_rate}
                onChange={e => setField('tax_rate', e.target.value)} />
              <Input label="Discount" id="discount" type="number" min="0"
                value={form.discount_amount}
                onChange={e => setField('discount_amount', e.target.value)}
                error={errors.discount_amount} />
            </div>

            {/* Summary */}
            <div className="space-y-1.5 text-sm min-w-52">
              <div className="flex justify-between text-slate-600">
                <span>Subtotal</span>
                <span>{form.currency} {subtotal.toLocaleString()}</span>
              </div>
              {taxAmt > 0 && (
                <div className="flex justify-between text-slate-600">
                  <span>Tax ({form.tax_rate}%)</span>
                  <span>{form.currency} {taxAmt.toLocaleString()}</span>
                </div>
              )}
              {discount > 0 && (
                <div className="flex justify-between text-green-600">
                  <span>Discount</span>
                  <span>− {form.currency} {discount.toLocaleString()}</span>
                </div>
              )}
              <div className="flex justify-between font-bold text-base text-slate-900 pt-2 border-t border-slate-200">
                <span>Total</span>
                <span>{form.currency} {Math.max(total, 0).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Bottom actions */}
      <div className="flex justify-between items-center">
        <button onClick={() => navigate('/billing')}
          className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1.5">
          <ArrowLeft size={14} /> Back to billing
        </button>
        <div className="flex items-center gap-2">
          <Button variant="secondary" isLoading={saving === 'draft'} disabled={!!saving}
            onClick={() => handleSave(false)}>
            <Save size={14} /> Save draft
          </Button>
          <Button isLoading={saving === 'issue'} disabled={!!saving}
            onClick={() => handleSave(true)}>
            <Send size={14} /> Issue invoice
          </Button>
        </div>
      </div>
    </div>
  );
}
