/**
 * services/api.ts
 * ================
 * Axios instance with:
 *  - JWT Bearer token injection on every request
 *  - Automatic token refresh on 401
 *  - Correlation ID header for request tracing
 *  - Structured error normalisation
 *  - Request/response logging in development
 */

import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
  AxiosResponse,
} from 'axios';
import { AuthTokens } from '../types';

// ─── Constants ───────────────────────────────────────────────────────────────
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';
const TOKEN_KEY   = 'hms_access';
const REFRESH_KEY = 'hms_refresh';

// ─── Token storage ────────────────────────────────────────────────────────────
// sessionStorage: cleared when the tab closes (better than localStorage for PHI)
export const tokenStorage = {
  getAccess:      ()    => sessionStorage.getItem(TOKEN_KEY),
  getRefresh:     ()    => sessionStorage.getItem(REFRESH_KEY),
  setTokens:      (t: AuthTokens) => {
    sessionStorage.setItem(TOKEN_KEY,   t.access);
    sessionStorage.setItem(REFRESH_KEY, t.refresh);
  },
  clearTokens:    ()    => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  },
};

// ─── Axios instance ───────────────────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    'Accept':       'application/json',
  },
});

// ─── Request interceptor — attach JWT + correlation ID ────────────────────────
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = tokenStorage.getAccess();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Attach a UUID so every request can be traced in server logs
    config.headers['X-Correlation-ID'] = crypto.randomUUID();
    return config;
  },
  (error) => Promise.reject(error),
);

// ─── Token refresh state ─────────────────────────────────────────────────────
let _isRefreshing = false;
let _refreshQueue: Array<{
  resolve: (token: string) => void;
  reject:  (err: unknown) => void;
}> = [];

function processRefreshQueue(error: unknown, token: string | null) {
  _refreshQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else       resolve(token!);
  });
  _refreshQueue = [];
}

// ─── Response interceptor — handle 401 with token refresh ─────────────────────
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Handle 401: attempt token refresh once
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (_isRefreshing) {
        // Queue request until refresh completes
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      _isRefreshing = true;
      const refreshToken = tokenStorage.getRefresh();

      if (!refreshToken) {
        _isRefreshing = false;
        tokenStorage.clearTokens();
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        const { data } = await axios.post<AuthTokens>(`${BASE_URL}/auth/refresh/`, {
          refresh: refreshToken,
        });
        tokenStorage.setTokens(data);
        processRefreshQueue(null, data.access);
        originalRequest.headers.Authorization = `Bearer ${data.access}`;
        return api(originalRequest);
      } catch (refreshError) {
        processRefreshQueue(refreshError, null);
        tokenStorage.clearTokens();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        _isRefreshing = false;
      }
    }

    // Normalise error shape
    return Promise.reject(normaliseError(error));
  },
);

// ─── Error normalisation ──────────────────────────────────────────────────────
export interface NormalisedError {
  status:    number;
  code:      string;
  message:   string;
  fields:    Record<string, string[]>;
  requestId: string;
}

function normaliseError(error: AxiosError): NormalisedError {
  const data = error.response?.data as any;
  const err  = data?.error ?? {};

  const detail = err.detail ?? error.message ?? 'An unexpected error occurred.';
  let message = typeof detail === 'string' ? detail : 'Validation error. Check the fields below.';
  let fields: Record<string, string[]> = {};

  if (typeof detail === 'object' && !Array.isArray(detail)) {
    fields = Object.entries(detail).reduce<Record<string, string[]>>(
      (acc, [k, v]) => ({
        ...acc,
        [k]: Array.isArray(v) ? v.map(String) : [String(v)],
      }),
      {},
    );
  }

  return {
    status:    error.response?.status ?? 0,
    code:      err.code ?? 'unknown_error',
    message,
    fields,
    requestId: err.request_id ?? '',
  };
}

export default api;
