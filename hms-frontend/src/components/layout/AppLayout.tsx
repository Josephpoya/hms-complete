/**
 * components/layout/AppLayout.tsx  (full rewrite)
 * =================================================
 * Persistent shell: collapsible sidebar + topbar + toast container.
 */

import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { ToastContainer } from '../ui/Toast';
import {
  LayoutDashboard, Users, Calendar, FileText, Pill,
  LogOut, Menu, X, Bell, Activity, User, Settings,
  ChevronDown, Shield,
} from 'lucide-react';
import { clsx } from 'clsx';

interface NavItem { label: string; href: string; icon: React.ReactNode; roles: string[]; }

const NAV: NavItem[] = [
  { label: 'Dashboard',    href: '/dashboard',    icon: <LayoutDashboard size={17} />, roles: ['admin','doctor','nurse','receptionist'] },
  { label: 'Patients',     href: '/patients',     icon: <Users            size={17} />, roles: ['admin','doctor','nurse','receptionist'] },
  { label: 'Appointments', href: '/appointments', icon: <Calendar         size={17} />, roles: ['admin','doctor','nurse','receptionist'] },
  { label: 'Billing',      href: '/billing',      icon: <FileText         size={17} />, roles: ['admin','receptionist'] },
  { label: 'Pharmacy',     href: '/pharmacy',     icon: <Pill             size={17} />, roles: ['admin','doctor','nurse'] },
];

const ROLE_PILL: Record<string, string> = {
  admin:        'bg-purple-100 text-purple-800',
  doctor:       'bg-blue-100 text-blue-800',
  nurse:        'bg-teal-100 text-teal-800',
  receptionist: 'bg-amber-100 text-amber-800',
};

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, payload, logout, can } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed]   = useState(false);
  const [userMenuOpen, setUserMenu] = useState(false);

  const visibleNav = NAV.filter(n => payload && n.roles.includes(payload.role));

  async function handleLogout() {
    await logout();
    navigate('/login');
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside className={clsx(
        'flex flex-col bg-slate-900 text-slate-100 transition-all duration-200 flex-shrink-0',
        collapsed ? 'w-[60px]' : 'w-[220px]',
      )}>
        {/* Brand */}
        <div className={clsx(
          'flex items-center gap-2.5 px-4 py-4 border-b border-slate-800 flex-shrink-0',
          collapsed && 'justify-center px-0',
        )}>
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <Activity size={15} className="text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="font-bold text-sm leading-tight">HMS</p>
              <p className="text-[10px] text-slate-400 truncate">Hospital System</p>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 overflow-y-auto overflow-x-hidden">
          {visibleNav.map(item => (
            <NavLink key={item.href} to={item.href}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 mx-2 my-0.5 py-2 rounded-lg text-sm transition-colors',
                collapsed ? 'justify-center px-0' : 'px-3',
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100',
              )}
              title={collapsed ? item.label : undefined}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {!collapsed && <span className="font-medium truncate">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="p-2 border-t border-slate-800 flex-shrink-0">
          {collapsed ? (
            <button onClick={handleLogout} title="Sign out"
              className="w-full flex justify-center p-2 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-red-400 transition-colors">
              <LogOut size={17} />
            </button>
          ) : (
            <div className="relative">
              <button onClick={() => setUserMenu(!userMenuOpen)}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-slate-800 transition-colors min-w-0">
                <div className="w-7 h-7 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 text-white text-xs font-bold">
                  {user?.email?.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-xs font-medium truncate leading-tight">{user?.email}</p>
                  <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', ROLE_PILL[payload?.role ?? ''])}>
                    {user?.role_display}
                  </span>
                </div>
                <ChevronDown size={12} className="text-slate-500 flex-shrink-0" />
              </button>

              {userMenuOpen && (
                <div className="absolute bottom-full left-0 right-0 mb-1 bg-white rounded-xl shadow-xl border border-slate-200 overflow-hidden z-50">
                  <button onClick={() => { setUserMenu(false); navigate('/profile'); }}
                    className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
                    <User size={14} className="text-slate-400" /> My profile
                  </button>
                  {can('users:manage') && (
                    <button onClick={() => { setUserMenu(false); navigate('/users'); }}
                      className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
                      <Shield size={14} className="text-slate-400" /> User management
                    </button>
                  )}
                  <div className="border-t border-slate-100" />
                  <button onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-red-600 hover:bg-red-50">
                    <LogOut size={14} /> Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* ── Main ────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Topbar */}
        <header className="flex-shrink-0 bg-white border-b border-slate-200 px-4 h-14 flex items-center gap-3">
          <button onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
            {collapsed ? <Menu size={17} /> : <X size={17} />}
          </button>

          <div className="flex-1" />

          <button className="relative p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
            <Bell size={17} />
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-red-500 rounded-full" />
          </button>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>

      {/* Global toast container */}
      <ToastContainer />
    </div>
  );
}
