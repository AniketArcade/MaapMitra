// Single typed API client for the app (mirrors frontend/lib/api.ts). Native app: it talks to
// FastAPI directly, authenticates with a bearer access token held in memory, and keeps the
// refresh token in secure storage (returned in the JSON body for `X-Client: mobile`).
import type { AuthResponse } from "@api-types";

import { API_ORIGIN } from "@/lib/config";
import { clearRefreshToken, getRefreshToken, setRefreshToken } from "@/lib/storage";

type ValidationIssue = { loc: (string | number)[]; msg: string };

const REQUEST_TIMEOUT_MS = 30_000; // Render free tier cold starts can take a while

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

/** status 0: the request never got an answer (offline, DNS, timeout, server down). */
export const NETWORK_ERROR_STATUS = 0;

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

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${API_ORIGIN}/api${path}`, { ...init, signal: controller.signal });
  } catch {
    throw new ApiError(
      NETWORK_ERROR_STATUS,
      "Can't reach the server. Check your connection and try again.",
    );
  } finally {
    clearTimeout(timer);
  }
}

function postRefresh(token: string): Promise<Response> {
  return rawFetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Client": "mobile" },
    body: JSON.stringify({ refresh_token: token }),
  });
}

/** Stores the session's tokens after login/register/refresh. */
export async function persistSession(session: AuthResponse): Promise<void> {
  accessToken = session.access_token;
  if (session.refresh_token) await setRefreshToken(session.refresh_token);
}

export async function dropSession(): Promise<void> {
  accessToken = null;
  await clearRefreshToken();
}

// Module-level single flight: concurrent 401s and the startup restore share one /auth/refresh,
// because refresh tokens rotate and a second parallel call would burn the first's new token.
let refreshInFlight: Promise<AuthResponse | null> | null = null;

/**
 * Restores/renews the session from the stored refresh token. Returns null when there is no valid
 * session. Only an explicit server 401 clears storage: a network failure throws instead, so a
 * flaky connection never logs the user out.
 */
export function refreshSession(): Promise<AuthResponse | null> {
  refreshInFlight ??= (async () => {
    const token = await getRefreshToken();
    if (!token) {
      accessToken = null;
      return null;
    }
    let res = await postRefresh(token);
    if (res.status === 401) {
      // Lost-race window: another refresh may have just rotated the token; re-read and retry once.
      const latest = await getRefreshToken();
      if (latest && latest !== token) res = await postRefresh(latest);
    }
    if (res.status === 401) {
      await dropSession();
      return null;
    }
    if (!res.ok) throw await toApiError(res);
    const session = (await res.json()) as AuthResponse;
    await persistSession(session);
    return session;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

type ApiOptions = { retried?: boolean };

export async function api<T>(path: string, init: RequestInit = {}, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Client", "mobile");
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  // FormData sets its own multipart boundary; never override it.
  if (init.body && !isForm && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const res = await rawFetch(path, { ...init, headers });

  if (res.status === 401 && !options.retried && !path.startsWith("/auth/")) {
    let session: AuthResponse | null = null;
    try {
      session = await refreshSession();
    } catch {
      // Refresh couldn't reach the server: surface the original 401 without ending the session.
    }
    if (session) return api<T>(path, init, { retried: true });
    // null token = refresh was rejected (dropSession ran); a network failure keeps the session.
    if (accessToken === null) onSessionExpired?.();
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** User-facing message for any thrown value. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "You don't have permission to do that.";
    if (err.status === 404) return "That item wasn't found, or you can't access it.";
    return err.message;
  }
  return "Something went wrong. Please try again.";
}
