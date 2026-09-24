/** API client.
 *
 * The token lives in sessionStorage rather than a cookie so that closing the
 * tab ends the session, and so no credential is sent automatically with
 * cross-site requests.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;
const TOKEN_KEY = "aegis.token";

/** What to say when the server refuses and says nothing useful about why.
 *
 *  A bare "500 Internal Server Error" is the status line, not an explanation:
 *  it puts a protocol detail in front of someone who wants to know whether
 *  their work is safe and what to do next. The server's own `detail` always
 *  wins over this -- these are only for the responses that carry none, which
 *  is exactly the 500 case.
 *
 *  None of these claim anything about what the request did or did not change.
 *  A 500 on a write can leave a partial commit behind, and an interface that
 *  says otherwise is guessing. */
function describeStatus(status: number, statusText: string): string {
  if (status === 502 || status === 503 || status === 504)
    return "The server is not reachable right now.";
  if (status >= 500) return "The server could not complete this request.";
  if (status === 404) return "That is not here.";
  if (status === 403) return "You do not have permission to do this.";
  if (status === 409) return "That conflicts with something already saved.";
  if (status === 413) return "That is larger than this endpoint accepts.";
  return statusText || "The request was refused.";
}

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
    let message = describeStatus(response.status, response.statusText);
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

  /** Fetch a file and hand it to the browser to save. The server's digest
   *  header is returned so the caller can show what was saved. */
  async download(path: string, fallbackName: string): Promise<{ sha256: string | null }> {
    const token = getToken();
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${API}${path}`, { headers, cache: "no-store" });
    if (response.status === 401) {
      setToken(null);
      throw new ApiError("Session expired. Sign in again.", 401);
    }
    if (!response.ok) {
      let message = describeStatus(response.status, response.statusText);
      try {
        const d = ((await response.json()) as { detail?: unknown }).detail;
        if (typeof d === "string") message = d;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(message, response.status);
    }
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
    return { sha256: response.headers.get("X-Content-SHA256") };
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
