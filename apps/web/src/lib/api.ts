/** API client.
 *
 * The token lives in sessionStorage rather than a cookie so that closing the
 * tab ends the session, and so no credential is sent automatically with
 * cross-site requests.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;
const TOKEN_KEY = "aegis.token";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session simply will not persist across reloads */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  // FormData sets its own Content-Type, including the multipart boundary. Naming
  // it here would produce a body the server cannot parse.
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API}${path}`, { ...init, headers, cache: "no-store" });

  if (response.status === 401) {
    setToken(null);
    throw new ApiError("Session expired. Sign in again.", 401);
  }
  if (!response.ok) {
    let detail: unknown;
    let message = `${response.status} ${response.statusText}`;
    try {
      detail = await response.json();
      const d = (detail as { detail?: unknown }).detail;
      if (typeof d === "string") message = d;
      else if (Array.isArray(d) && d.length) message = String((d[0] as any)?.msg ?? message);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),

  /** Multipart upload. `query` carries the scalar fields the endpoint reads
   *  from the query string rather than the form body. */
  upload: <T>(path: string, file: File, query: Record<string, string> = {}) => {
    const form = new FormData();
    form.append("file", file);
    const search = new URLSearchParams(
      Object.entries(query).filter(([, value]) => value !== ""),
    ).toString();
    return request<T>(search ? `${path}?${search}` : path, { method: "POST", body: form });
  },

  async login(email: string, password: string) {
    const body = await request<{ access_token: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    setToken(body.access_token);
    return body;
  },

  logout() {
    setToken(null);
  },
};

export const apiBase = BASE;
