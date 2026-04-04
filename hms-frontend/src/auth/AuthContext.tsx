/**
 * auth/AuthContext.tsx
 * ====================
 * Central auth state. Provides:
 *   - user (decoded JWT payload + full User profile)
 *   - login / logout helpers
 *   - role-checking helpers (can(), isRole())
 *   - automatic session validation on mount
 */

import React, { createContext, useContext, useEffect, useReducer, useCallback } from 'react';
import { User, TokenPayload, Role } from '../types';
import { authService } from '../services/authService';

// ─── Permission matrix ────────────────────────────────────────────────────────
type Permission =
  | 'patients:read'   | 'patients:write'  | 'patients:delete'
  | 'records:read'    | 'records:write'
  | 'appointments:read' | 'appointments:write' | 'appointments:status'
  | 'billing:read'    | 'billing:write'
  | 'pharmacy:read'   | 'prescriptions:write' | 'pharmacy:dispense'
  | 'users:manage'    | 'audit:read'       | 'reports:read'
  | 'drugs:write';

const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: [
    'patients:read', 'patients:write', 'patients:delete',
    'records:read',  'records:write',
    'appointments:read', 'appointments:write', 'appointments:status',
    'billing:read',  'billing:write',
    'pharmacy:read', 'prescriptions:write', 'pharmacy:dispense', 'drugs:write',
    'users:manage',  'audit:read', 'reports:read',
  ],
  doctor: [
    'patients:read',
    'records:read', 'records:write',
    'appointments:read', 'appointments:status',
    'billing:read',
    'pharmacy:read', 'prescriptions:write',
  ],
  nurse: [
    'patients:read',
    'records:read', 'records:write',
    'appointments:read', 'appointments:status',
    'billing:read',
    'pharmacy:read', 'pharmacy:dispense',
  ],
  receptionist: [
    'patients:read', 'patients:write',
    'appointments:read', 'appointments:write',
    'billing:read',  'billing:write',
    'pharmacy:read',
  ],
};

// ─── State ────────────────────────────────────────────────────────────────────
interface AuthState {
  user:        User | null;
  payload:     TokenPayload | null;
  isLoading:   boolean;
  isAuthenticated: boolean;
}

type AuthAction =
  | { type: 'LOADING' }
  | { type: 'LOGIN_SUCCESS'; user: User; payload: TokenPayload }
  | { type: 'LOGOUT' }
  | { type: 'UPDATE_USER'; user: User };

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'LOADING':
      return { ...state, isLoading: true };
    case 'LOGIN_SUCCESS':
      return { user: action.user, payload: action.payload, isLoading: false, isAuthenticated: true };
    case 'LOGOUT':
      return { user: null, payload: null, isLoading: false, isAuthenticated: false };
    case 'UPDATE_USER':
      return { ...state, user: action.user };
    default:
      return state;
  }
}

// ─── Context ──────────────────────────────────────────────────────────────────
interface AuthContextValue extends AuthState {
  login:   (email: string, password: string) => Promise<void>;
  logout:  () => Promise<void>;
  can:     (permission: Permission) => boolean;
  isRole:  (...roles: Role[]) => boolean;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ─── Provider ─────────────────────────────────────────────────────────────────
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, {
    user: null, payload: null, isLoading: true, isAuthenticated: false,
  });

  // On mount: check if a valid session exists
  useEffect(() => {
    const payload = authService.getCurrentPayload();
    if (!payload) {
      dispatch({ type: 'LOGOUT' });
      return;
    }
    // Fetch full user profile
    authService.getMe()
      .then(user => dispatch({ type: 'LOGIN_SUCCESS', user, payload }))
      .catch(() => dispatch({ type: 'LOGOUT' }));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    dispatch({ type: 'LOADING' });
    const { user: payload } = await authService.login(email, password);
    const user = await authService.getMe();
    dispatch({ type: 'LOGIN_SUCCESS', user, payload });
  }, []);

  const logout = useCallback(async () => {
    await authService.logout();
    dispatch({ type: 'LOGOUT' });
  }, []);

  const can = useCallback((permission: Permission): boolean => {
    if (!state.payload) return false;
    return ROLE_PERMISSIONS[state.payload.role]?.includes(permission) ?? false;
  }, [state.payload]);

  const isRole = useCallback((...roles: Role[]): boolean => {
    if (!state.payload) return false;
    return roles.includes(state.payload.role);
  }, [state.payload]);

  const refreshUser = useCallback(async () => {
    const user = await authService.getMe();
    dispatch({ type: 'UPDATE_USER', user });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout, can, isRole, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
