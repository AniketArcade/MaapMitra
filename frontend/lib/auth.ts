"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, refreshSession, setAccessToken, setSessionExpiredHandler } from "@/lib/api";
import type { AuthResponse, RegisterRequest, User } from "@/lib/types";

type Status = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  user: User | null;
  status: Status;
  login: (email: string, password: string) => Promise<User>;
  register: (body: RegisterRequest) => Promise<User>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  const applySession = useCallback((session: AuthResponse | null) => {
    setAccessToken(session?.access_token ?? null);
    setUser(session?.user ?? null);
    setStatus(session ? "authenticated" : "anonymous");
  }, []);

  // The access token isn't persisted, so every page load restores the session via refresh.
  useEffect(() => {
    let cancelled = false;
    void refreshSession().then((session) => {
      if (!cancelled) applySession(session);
    });
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  useEffect(() => {
    setSessionExpiredHandler(() => {
      applySession(null);
      router.replace("/login");
    });
    return () => setSessionExpiredHandler(null);
  }, [applySession, router]);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api<AuthResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      applySession(session);
      return session.user;
    },
    [applySession],
  );

  const register = useCallback(
    async (body: RegisterRequest) => {
      const session = await api<AuthResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      });
      applySession(session);
      return session.user;
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await api<void>("/auth/logout", { method: "POST" });
    } finally {
      applySession(null);
      router.replace("/login");
    }
  }, [applySession, router]);

  const value = useMemo(
    () => ({ user, status, login, register, logout }),
    [user, status, login, register, logout],
  );
  return createElement(AuthContext.Provider, { value }, children);
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Only allow same-site relative paths as post-login redirects (no open redirects). */
export function safeNextPath(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}
