import type { AuthResponse, RegisterRequest, User } from "@api-types";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  api,
  ApiError,
  dropSession,
  NETWORK_ERROR_STATUS,
  persistSession,
  refreshSession,
  setSessionExpiredHandler,
} from "@/lib/api";
import { isMobileRole } from "@/lib/nav";
import { getRefreshToken } from "@/lib/storage";

// "offline": a stored session exists but the server couldn't be reached (kept, not discarded).
type Status = "loading" | "authenticated" | "anonymous" | "offline";

export const ADMIN_NOTICE = "Admin accounts are available on the website.";

type AuthContextValue = {
  user: User | null;
  status: Status;
  /** One-shot message for the login screen (e.g. admin blocked, session ended). */
  notice: string | null;
  clearNotice: () => void;
  login: (email: string, password: string) => Promise<User | null>;
  register: (body: RegisterRequest) => Promise<User | null>;
  logout: () => Promise<void>;
  retry: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function serverLogout(): Promise<void> {
  const token = await getRefreshToken();
  if (!token) return;
  try {
    await api<void>("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: token }) });
  } catch {
    // best effort: the local session is dropped regardless
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [notice, setNotice] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  /** Applies a session; admin roles are web-only, so they are signed out again immediately. */
  const applySession = useCallback(async (session: AuthResponse | null): Promise<User | null> => {
    if (session && !isMobileRole(session.user.role)) {
      await serverLogout();
      await dropSession();
      setUser(null);
      setStatus("anonymous");
      setNotice(ADMIN_NOTICE);
      return null;
    }
    setUser(session?.user ?? null);
    setStatus(session ? "authenticated" : "anonymous");
    return session?.user ?? null;
  }, []);

  // The access token isn't persisted: every app start restores the session from the refresh token.
  useEffect(() => {
    let cancelled = false;
    refreshSession()
      .then((session) => (cancelled ? null : applySession(session)))
      .catch((err: unknown) => {
        if (cancelled) return;
        // Server unreachable: keep the stored session and let the user retry.
        if (err instanceof ApiError && err.status === NETWORK_ERROR_STATUS) setStatus("offline");
        else setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, [applySession, attempt]);

  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null);
      setStatus("anonymous");
      setNotice("Your session has ended. Please sign in again.");
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api<AuthResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      await persistSession(session);
      setNotice(null);
      return applySession(session);
    },
    [applySession],
  );

  const register = useCallback(
    async (body: RegisterRequest) => {
      const session = await api<AuthResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      });
      await persistSession(session);
      setNotice(null);
      return applySession(session);
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    await serverLogout();
    await dropSession();
    setUser(null);
    setStatus("anonymous");
    setNotice(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      notice,
      clearNotice: () => setNotice(null),
      login,
      register,
      logout,
      retry: () => {
        setStatus("loading");
        setAttempt((n) => n + 1);
      },
    }),
    [user, status, notice, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
