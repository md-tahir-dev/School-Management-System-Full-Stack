import type { TokenResponse } from "./types";

// Same-origin by default: Next rewrites /api/v1/* to FastAPI (see next.config.mjs).
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    /** Field-level validation messages, keyed by input name (e.g. "guardian.father_cnic"). */
    public fields?: Record<string, string>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Toast text for a failed mutation: the first field error if any, else the API message, else `fallback`. */
export function errorText(e: unknown, fallback: string) {
  return e instanceof ApiError ? Object.values(e.fields ?? {})[0] ?? e.message : fallback;
}

// The access token lives in memory only (never localStorage). The httpOnly refresh cookie
// restores it after a page reload.
let accessToken: string | null = null;
export const setAccessToken = (token: string | null) => {
  accessToken = token;
};

let sessionExpiredHandler: (() => void) | null = null;
export const setSessionExpiredHandler = (fn: (() => void) | null) => {
  sessionExpiredHandler = fn;
};

async function toApiError(res: Response): Promise<ApiError> {
  // API error shape: { detail, code, fields?, details?, request_id? }
  let body: { detail?: string; code?: string; fields?: Record<string, string>; details?: unknown } | null = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body */
  }
  return new ApiError(
    res.status,
    body?.code ?? `HTTP_${res.status}`,
    typeof body?.detail === "string" ? body.detail : "Something went wrong. Please try again.",
    body?.details,
    body?.fields,
  );
}

let refreshInFlight: Promise<TokenResponse | null> | null = null;

/** Exchanges the refresh cookie for a new access token. Single-flight, so parallel 401s and React
 * strict-mode double effects share one request (refresh tokens rotate; two calls would race).
 * Resolves null when there is no valid session; rejects on network/server errors. */
export function refreshSession(): Promise<TokenResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" });
        if (res.status === 401) {
          setAccessToken(null);
          return null;
        }
        if (!res.ok) throw await toApiError(res);
        const data = (await res.json()) as TokenResponse;
        setAccessToken(data.access_token);
        return data;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

type QueryValue = string | number | boolean | null | undefined;
interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, QueryValue>;
  /** Set false for endpoints that don't need (or must not retry with) a bearer token. */
  auth?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Record<string, QueryValue>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, auth = true, signal } = opts;
  const url = buildUrl(path, query);

  const send = () => {
    const headers: Record<string, string> = {};
    // FormData (file uploads): the browser sets the multipart boundary itself.
    const isForm = body instanceof FormData;
    if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    return fetch(url, {
      method,
      headers,
      credentials: "include",
      signal,
      body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await send();

  // Expired access token: refresh once and retry.
  if (res.status === 401 && auth) {
    const peek = (await res
      .clone()
      .json()
      .catch(() => null)) as { code?: string } | null;
    if (peek?.code === "INVALID_TOKEN" || peek?.code === "UNAUTHORIZED") {
      const session = await refreshSession();
      if (session) res = await send();
      else sessionExpiredHandler?.();
    }
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- auth endpoints -------------------------------------------------------
export async function loginRequest(username: string, password: string) {
  const data = await api<TokenResponse>("/auth/login", { method: "POST", body: { username, password }, auth: false });
  setAccessToken(data.access_token);
  return data;
}

export async function logoutRequest() {
  try {
    await api<void>("/auth/logout", { method: "POST", auth: false });
  } finally {
    setAccessToken(null);
  }
}

export async function changePasswordRequest(current_password: string, new_password: string) {
  const data = await api<TokenResponse>("/auth/change-password", {
    method: "POST",
    body: { current_password, new_password },
  });
  setAccessToken(data.access_token);
  return data;
}

/** Authenticated binary/text download (PDF, CSV). Mirrors `api()`: bearer token plus one refresh retry. */
export async function apiBlob(path: string, query?: Record<string, QueryValue>): Promise<Blob> {
  const url = buildUrl(path, query);
  const send = () =>
    fetch(url, { credentials: "include", headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {} });
  let res = await send();
  if (res.status === 401) {
    const session = await refreshSession();
    if (session) res = await send();
    else sessionExpiredHandler?.();
  }
  if (!res.ok) throw await toApiError(res);
  return res.blob();
}

export function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

/** Downloads a login-only upload (diary attachment, homework, material) by its stored `/api/v1/uploads/...`
 * URL. A plain <a href> can't send the in-memory bearer token. */
export async function downloadFile(url: string) {
  const path = url.replace(/^\/api\/v1/, "");
  saveBlob(await apiBlob(path), path.split("/").pop() || "file");
}

export function openBlob(blob: Blob) {
  const href = URL.createObjectURL(blob);
  window.open(href, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(href), 60_000);
}
