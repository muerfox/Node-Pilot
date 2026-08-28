import type { ApiErrorBody } from "@/types/api";

const API_BASE = "/api/v1/";
const REFRESH_STORAGE_KEY = "nodepilot_refresh";

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// The JWT access token lives in memory only (never localStorage) to keep
// it out of reach of any XSS-exfiltration-via-storage vector; it's lost
// on a hard refresh, which triggers one silent refresh-token exchange
// (see AuthProvider). The refresh token itself is longer-lived and the
// backend has no httpOnly-cookie delivery path (section 32 returns it in
// the login response body), so it's kept in localStorage as the
// pragmatic tradeoff -- see docs/architecture.md's frontend notes.
let accessToken: string | null = null;
let onAuthExpired: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function setAuthExpiredHandler(handler: (() => void) | null) {
  onAuthExpired = handler;
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_STORAGE_KEY);
}

export function setStoredRefreshToken(token: string | null) {
  if (token) localStorage.setItem(REFRESH_STORAGE_KEY, token);
  else localStorage.removeItem(REFRESH_STORAGE_KEY);
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refresh = getStoredRefreshToken();
  if (!refresh) return false;

  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE}auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    })
      .then(async (res) => {
        if (!res.ok) return false;
        const data = await res.json();
        setAccessToken(data.access);
        if (data.refresh) setStoredRefreshToken(data.refresh); // ROTATE_REFRESH_TOKENS is on server-side
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(path.replace(/^\//, ""), window.location.origin + API_BASE);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
  }
  return url.pathname + url.search;
}

async function rawRequest<T>(path: string, options: RequestOptions, retryOn401 = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(buildUrl(path, options.params), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (response.status === 401 && retryOn401) {
    const refreshed = await tryRefresh();
    if (refreshed) return rawRequest<T>(path, options, false);
    onAuthExpired?.();
    throw new ApiError(401, "AUTH_EXPIRED", "Your session has expired. Please log in again.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : undefined;

  if (!response.ok) {
    const body = data as ApiErrorBody | undefined;
    throw new ApiError(response.status, body?.error?.code ?? "UNKNOWN", body?.error?.message ?? response.statusText, body?.error?.details ?? {});
  }

  return data as T;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"], signal?: AbortSignal) => rawRequest<T>(path, { method: "GET", params, signal }),
  post: <T>(path: string, body?: unknown, idempotencyKey?: string) => rawRequest<T>(path, { method: "POST", body, idempotencyKey }),
  patch: <T>(path: string, body?: unknown) => rawRequest<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: unknown) => rawRequest<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => rawRequest<T>(path, { method: "DELETE" }),
};

export function wsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(path, `${proto}//${window.location.host}`);
  if (accessToken) url.searchParams.set("token", accessToken);
  return url.toString();
}
