// API client for the Aria operations console.

import type { Borrower, PastCall, Payment, Stats } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json();
}

async function apiPost<T>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} failed: ${res.status} ${text}`);
  }
  return res.json();
}


// ─── Borrowers ───────────────────────────────────────────

export type BorrowerFilters = {
  status?: string;
  risk_tier?: string;
  intent?: string;
  sort?: string;
};

export async function listBorrowers(
  filters: BorrowerFilters = {},
): Promise<{ borrowers: Borrower[]; count: number }> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.risk_tier) params.set("risk_tier", filters.risk_tier);
  if (filters.intent) params.set("intent", filters.intent);
  if (filters.sort) params.set("sort", filters.sort);

  const qs = params.toString();
  return apiGet(`/api/borrowers${qs ? `?${qs}` : ""}`);
}

export async function getBorrower(id: string): Promise<Borrower> {
  return apiGet(`/api/borrowers/${encodeURIComponent(id)}`);
}

export async function getBorrowerCalls(
  id: string,
): Promise<{ calls: PastCall[]; count: number }> {
  return apiGet(`/api/borrowers/${encodeURIComponent(id)}/calls`);
}

export async function getBorrowerPayments(
  id: string,
): Promise<{ payments: Payment[]; count: number }> {
  return apiGet(`/api/borrowers/${encodeURIComponent(id)}/payments`);
}

export async function callBorrower(
  id: string,
): Promise<{ call_sid: string; to: string; borrower_name: string }> {
  return apiPost(`/api/borrowers/${encodeURIComponent(id)}/call`);
}


// ─── Stats ───────────────────────────────────────────────

export async function getStats(): Promise<Stats> {
  return apiGet(`/api/stats`);
}
