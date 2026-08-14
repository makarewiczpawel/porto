import type { ApiErrorBody } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody | null, fallback: string) {
    super(body?.error?.message ?? fallback);
    this.status = status;
    this.code = body?.error?.code ?? "UNKNOWN";
    this.details = body?.error?.details ?? {};
  }
}

/** Access token lives in memory only. The refresh token is an httpOnly cookie,
 *  so a lost tab means one silent refresh, not a lost session. */
let accessToken: string | null = null;
let onLogout: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function setLogoutHandler(handler: () => void) {
  onLogout = handler;
}

async function parse(response: Response) {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

let refreshing: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/api/auth/refresh`, { method: "POST", credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return false;
        const body = await response.json();
        accessToken = body.access_token;
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  retry?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, retry = true } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && retry && !path.startsWith("/api/auth/refresh")) {
    // One silent refresh, then give up and send the user to the login screen.
    if (await refreshOnce()) {
      return request<T>(path, { ...options, retry: false });
    }
    accessToken = null;
    onLogout?.();
  }

  if (!response.ok) {
    throw new ApiError(response.status, (await parse(response)) as ApiErrorBody | null, response.statusText);
  }
  return (await parse(response)) as T;
}

/**
 * Pobranie pliku, nie JSON-a — eksport bazy.
 *
 * Nie da się tego zrobić zwykłym linkiem: adres wymaga nagłówka z tokenem,
 * którego `<a href>` nie potrafi dołożyć. Stąd pobranie przez `fetch` i
 * podanie gotowej zawartości przeglądarce.
 */
export async function requestBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let response = await fetch(`${BASE}${path}`, { headers, credentials: "include" });
  if (response.status === 401 && (await refreshOnce())) {
    const retryHeaders: Record<string, string> = {};
    if (accessToken) retryHeaders.Authorization = `Bearer ${accessToken}`;
    response = await fetch(`${BASE}${path}`, { headers: retryHeaders, credentials: "include" });
  }
  if (!response.ok) {
    throw new ApiError(response.status, null, "Nie udało się pobrać pliku.");
  }
  return response.blob();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  blob: (path: string) => requestBlob(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export { BASE as API_BASE };
