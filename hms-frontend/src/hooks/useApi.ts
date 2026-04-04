/**
 * hooks/useApi.ts
 * ================
 * Generic data-fetching hooks that wrap fetch lifecycle:
 * loading, error, refetch, pagination.
 *
 * useQuery    — single fetch, auto-runs on mount + dep changes
 * useMutation — imperative trigger, returns loading + error state
 * usePaginatedQuery — handles paginated API responses
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { PaginatedResponse } from '../types';
import { NormalisedError } from '../services/api';

// ─── useQuery ────────────────────────────────────────────────────────────────
interface QueryState<T> {
  data:     T | null;
  loading:  boolean;
  error:    string;
  refetch:  () => void;
}

export function useQuery<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): QueryState<T> {
  const [data,    setData]    = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');
  const mountedRef = useRef(true);

  const run = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await fetcher();
      if (mountedRef.current) setData(result);
    } catch (e: any) {
      if (mountedRef.current) setError(e?.message ?? 'An error occurred.');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    run();
    return () => { mountedRef.current = false; };
  }, [run]);

  return { data, loading, error, refetch: run };
}

// ─── useMutation ─────────────────────────────────────────────────────────────
interface MutationState<TResult, TInput> {
  mutate:   (input: TInput) => Promise<TResult | null>;
  loading:  boolean;
  error:    string;
  fieldErrors: Record<string, string[]>;
  reset:    () => void;
}

export function useMutation<TResult, TInput = void>(
  mutFn: (input: TInput) => Promise<TResult>,
  options?: {
    onSuccess?: (result: TResult) => void;
    onError?:   (err: NormalisedError) => void;
  },
): MutationState<TResult, TInput> {
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const reset = useCallback(() => {
    setError('');
    setFieldErrors({});
  }, []);

  const mutate = useCallback(async (input: TInput): Promise<TResult | null> => {
    setLoading(true);
    reset();
    try {
      const result = await mutFn(input);
      options?.onSuccess?.(result);
      return result;
    } catch (e: any) {
      const err = e as NormalisedError;
      setError(err?.message ?? 'An error occurred.');
      setFieldErrors(err?.fields ?? {});
      options?.onError?.(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [mutFn, options, reset]);

  return { mutate, loading, error, fieldErrors, reset };
}

// ─── usePaginatedQuery ────────────────────────────────────────────────────────
interface PaginatedState<T> {
  data:     PaginatedResponse<T> | null;
  loading:  boolean;
  error:    string;
  page:     number;
  setPage:  (p: number) => void;
  refetch:  () => void;
}

export function usePaginatedQuery<T>(
  fetcher: (page: number) => Promise<PaginatedResponse<T>>,
  deps: unknown[] = [],
): PaginatedState<T> {
  const [page, setPage] = useState(1);
  const { data, loading, error, refetch } = useQuery(
    () => fetcher(page),
    [page, ...deps],
  );
  return { data, loading, error, page, setPage, refetch };
}

// ─── useDebounce ──────────────────────────────────────────────────────────────
export function useDebounce<T>(value: T, ms = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

// ─── useToast ─────────────────────────────────────────────────────────────────
type ToastVariant = 'success' | 'error' | 'info' | 'warning';

interface Toast { id: string; message: string; variant: ToastVariant; }

// Simple module-level toast state (avoids need for a full context)
let _setToasts: React.Dispatch<React.SetStateAction<Toast[]>> | null = null;

export function toast(message: string, variant: ToastVariant = 'info') {
  if (!_setToasts) return;
  const id = crypto.randomUUID();
  _setToasts(prev => [...prev, { id, message, variant }]);
  setTimeout(() => {
    _setToasts?.(prev => prev.filter(t => t.id !== id));
  }, 4000);
}

export function useToastState() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  _setToasts = setToasts;
  return toasts;
}
