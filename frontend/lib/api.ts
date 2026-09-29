// Single typed API client. Client-side only: it calls the same-origin /api/* rewrite.
import type { ApplicationStats, AuthResponse } from "@/lib/types";

type ValidationIssue = { loc: (string | number)[]; msg: string };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

// The access token lives in memory only. It is never persisted or put in a URL.
let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail: unknown = null;
  try {
    detail = ((await res.json()) as { detail?: unknown }).detail;
  } catch {
    // non-JSON body
  }
  if (res.status === 422 && Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const issue of detail as ValidationIssue[]) {
      const field = issue.loc.at(-1);
      if (typeof field === "string") fieldErrors[field] = issue.msg.replace(/^Value error, /, "");
    }
    return new ApiError(422, "Please fix the highlighted fields.", fieldErrors);
  }
  const message =
    typeof detail === "string"
      ? detail
      : res.status === 429
        ? "Too many attempts. Please wait a minute and try again."
        : "Something went wrong. Please try again.";
  return new ApiError(res.status, message);
}

function postRefresh(): Promise<Response> {
  return fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
}

// Module-level single flight: every caller (including StrictMode's double mount and
// concurrent 401s) shares one /auth/refresh request.
let refreshInFlight: Promise<AuthResponse | null> | null = null;

export function refreshSession(): Promise<AuthResponse | null> {
  refreshInFlight ??= (async () => {
    try {
      let res = await postRefresh();
      // A 401 can mean another tab won a rotation race and already set a fresh cookie.
      if (res.status === 401) res = await postRefresh();
      if (!res.ok) {
        accessToken = null;
        return null;
      }
      const data = (await res.json()) as AuthResponse;
      accessToken = data.access_token;
      return data;
    } catch {
      accessToken = null;
      return null;
    }
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

type ApiOptions = {
  /** Absolute origin for this call (upload fallback); default is the same-origin /api rewrite. */
  origin?: string;
  retried?: boolean;
};

export async function api<T>(path: string, init: RequestInit = {}, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  // FormData sets its own multipart boundary; never override it.
  if (init.body && !isForm && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const origin = options.origin ?? "";
  const res = await fetch(`${origin}/api${path}`, {
    ...init,
    headers,
    // Cross-origin calls authenticate with the bearer header only; cookies stay first-party.
    credentials: origin ? "omit" : "same-origin",
  });

  if (res.status === 401 && !options.retried && !path.startsWith("/auth/")) {
    if (await refreshSession()) return api<T>(path, init, { ...options, retried: true });
    onSessionExpired?.();
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Uploads go straight to Render when NEXT_PUBLIC_UPLOAD_ORIGIN is set (fallback if the
 *  Vercel rewrite caps request bodies); otherwise through the /api rewrite like everything else. */
export function uploadDocument<T>(form: FormData): Promise<T> {
  const origin = process.env.NEXT_PUBLIC_UPLOAD_ORIGIN || undefined;
  return api<T>("/documents", { method: "POST", body: form }, { origin });
}

// Not cached like getApplicationMeta/getInstrumentMeta: dashboard sections refetch this
// on retry and on tab focus, so a stale cached promise would defeat both.
export function getApplicationStats(): Promise<ApplicationStats> {
  return api<ApplicationStats>("/applications/stats");
}
