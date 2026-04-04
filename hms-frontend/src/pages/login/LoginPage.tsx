import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Activity, Eye, EyeOff, AlertCircle } from 'lucide-react';

interface LoginForm { email: string; password: string; }

export function LoginPage() {
  const { login } = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();
  const from       = (location.state as any)?.from?.pathname ?? '/dashboard';
  const [form, setForm] = useState<LoginForm>({ email: '', password: '' });
  const [showPw, setShowPw]       = useState(false);
  const [serverErr, setServerErr] = useState('');
  const [loading, setLoading]     = useState(false);
  const [errors, setErrors]       = useState<Partial<LoginForm>>({});

  function validate() {
    const e: Partial<LoginForm> = {};
    if (!form.email)    e.email    = 'Email is required.';
    else if (!/\S+@\S+\.\S+/.test(form.email)) e.email = 'Enter a valid email.';
    if (!form.password) e.password = 'Password is required.';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    setLoading(true); setServerErr('');
    try {
      await login(form.email, form.password);
      navigate(from, { replace: true });
    } catch (err: any) {
      setServerErr(err?.message ?? 'Login failed. Please check your credentials.');
    } finally { setLoading(false); }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4 shadow-lg">
            <Activity size={32} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Hospital Management</h1>
          <p className="text-blue-300 text-sm mt-1">Secure staff portal</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-slate-900 mb-6">Sign in to your account</h2>

          {serverErr && (
            <div className="flex items-start gap-2.5 p-3 mb-5 bg-red-50 border border-red-200 rounded-lg">
              <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-700">{serverErr}</p>
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">Email address</label>
              <input type="email" autoComplete="email" placeholder="you@hospital.com"
                value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className={`w-full rounded-lg border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 transition-colors ${errors.email ? 'border-red-400 focus:ring-red-200' : 'border-slate-300 focus:ring-blue-200 focus:border-blue-500'}`}
              />
              {errors.email && <p className="mt-1.5 text-xs text-red-600">{errors.email}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} autoComplete="current-password"
                  value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  className={`w-full rounded-lg border px-3.5 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 transition-colors ${errors.password ? 'border-red-400 focus:ring-red-200' : 'border-slate-300 focus:ring-blue-200 focus:border-blue-500'}`}
                />
                <button type="button" onClick={() => setShowPw(!showPw)} tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && <p className="mt-1.5 text-xs text-red-600">{errors.password}</p>}
            </div>

            <button type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 px-4 rounded-lg transition-colors disabled:opacity-60">
              {loading ? (
                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Signing in…</>
              ) : 'Sign in'}
            </button>
          </form>

          <p className="text-center text-xs text-slate-500 mt-6">
            Restricted to authorised hospital staff only.<br />
            Contact IT if you need access.
          </p>
        </div>
        <p className="text-center text-xs text-blue-400 mt-6">All access is monitored and logged.</p>
      </div>
    </div>
  );
}
