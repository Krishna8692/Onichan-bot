/**
 * API client helpers for the Onichan Web Panel.
 * All routes go through the Flask API server.
 */

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

async function apiFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  return res;
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as any).message || (data as any).error || `HTTP ${res.status}`);
  }
  return data as T;
}

// ─── Auth ─────────────────────────────────────────────────────────────────

export interface MeResponse {
  user_id: string;
  username: string;
  first_name?: string;
  is_admin?: boolean;
  is_premium?: boolean;
  approved?: boolean;
}

export async function getMe(): Promise<MeResponse | null> {
  try {
    const res = await apiFetch('/api/user/me');
    if (res.status === 401) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ─── Stats ────────────────────────────────────────────────────────────────

export async function getStats() {
  return apiGet('/api/stats');
}

// ─── Hitter APIs ─────────────────────────────────────────────────────────

export interface HitRequest {
  card: string;
  url: string;
  proxy?: string;
}

export interface HitResult {
  status: 'live' | 'decline' | '3ds' | 'error';
  message: string;
  gateway: string;
  time_taken: number;
}

const HITTER_ENDPOINTS: Record<string, string> = {
  auto: '/api/tools/hit',
  hitck: '/api/tools/hitck',
  hitad: '/api/tools/hitad',
  hitmpgs: '/api/tools/hitmpgs',
  hitwhop: '/api/tools/hitwhop',
  hitpad: '/api/tools/hitpad',
  hitep: '/api/tools/hitep',
  jio: '/api/tools/jio',
};

export async function runHitter(gateway: string, payload: HitRequest): Promise<HitResult> {
  const ep = HITTER_ENDPOINTS[gateway] || '/api/tools/hit';
  return apiPost<HitResult>(ep, payload);
}

// ─── CC Tools ─────────────────────────────────────────────────────────────

export interface GenResult {
  cards: string[];
  count: number;
  bin: string;
  brand: string;
}

export async function genCards(bin: string, count: number): Promise<GenResult> {
  return apiGet<GenResult>(`/api/tools/gen?bin=${encodeURIComponent(bin)}&count=${count}`);
}

export interface FakeResult {
  name?: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  zip?: string;
  country?: string;
  [key: string]: unknown;
}

export async function genFake(country: string): Promise<FakeResult> {
  return apiGet<FakeResult>(`/api/tools/fake?country=${encodeURIComponent(country)}`);
}

export interface IbanResult {
  iban: string;
  country: string;
  flag: string;
  bic: string;
  bank: string;
  country_code: string;
}

export async function genIban(country?: string): Promise<IbanResult> {
  const q = country ? `?country=${encodeURIComponent(country)}` : '';
  return apiGet<IbanResult>(`/api/tools/iban${q}`);
}

export interface CleanResult {
  cards: string[];
  count: number;
  dupes: number;
  stats: Record<string, unknown>;
}

export async function cleanCards(text: string): Promise<CleanResult> {
  return apiPost<CleanResult>('/api/tools/clean', { text });
}

export interface PickResult {
  cards: string[];
  count: number;
  total: number;
}

export async function pickCards(text: string, count: number): Promise<PickResult> {
  return apiPost<PickResult>('/api/tools/pick', { text, count });
}

// ─── Wallet ───────────────────────────────────────────────────────────────

export async function getWalletBalance() {
  return apiGet('/api/wallet/internal-balance');
}

export async function getDepositAddresses() {
  return apiGet('/api/wallet/deposit-addresses');
}

export async function getTransactions() {
  return apiGet('/api/wallet/transactions');
}
