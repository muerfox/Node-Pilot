import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, getStoredRefreshToken, setAccessToken, setAuthExpiredHandler, setStoredRefreshToken } from "@/lib/api";
import type { User } from "@/types/api";

interface AuthContextValue {
  user: User | null;
  status: "loading" | "authenticated" | "unauthenticated";
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");

  const logout = useCallback(() => {
    setAccessToken(null);
    setStoredRefreshToken(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await api.post<{ access: string; refresh: string }>("auth/login/", { username, password });
    setAccessToken(tokens.access);
    setStoredRefreshToken(tokens.refresh);
    const me = await api.get<User>("users/me/");
    setUser(me);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    setAuthExpiredHandler(logout);
    return () => setAuthExpiredHandler(null);
  }, [logout]);

  // On a hard refresh there's no access token in memory yet, but the
  // refresh token in localStorage can silently mint a new one -- the
  // http layer's own 401 handling already does this, so a single
  // authenticated request is enough to bootstrap the session.
  useEffect(() => {
    if (!getStoredRefreshToken()) {
      setStatus("unauthenticated");
      return;
    }
    api
      .get<User>("users/me/")
      .then((me) => {
        setUser(me);
        setStatus("authenticated");
      })
      .catch(() => {
        setStatus("unauthenticated");
      });
  }, []);

  return <AuthContext.Provider value={{ user, status, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
