import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, setAccessToken, setLogoutHandler } from "@/api/client";
import type { AuthResponse, Settings, User } from "@/api/types";

interface AuthValue {
  user: User | null;
  settings: Settings | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (body: { email: string; password: string; display_name: string; invite_code: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/** Not a credential — just a marker so a first-ever visit does not fire a
 *  refresh request that is guaranteed to 401. */
const SESSION_MARK = "porto.session";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [ready, setReady] = useState(false);

  const clear = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setSettings(null);
    localStorage.removeItem(SESSION_MARK);
  }, []);

  const refreshMe = useCallback(async () => {
    const me = await api.get<{ user: User; settings: Settings }>("/api/auth/me");
    setUser(me.user);
    setSettings(me.settings);
  }, []);

  useEffect(() => {
    setLogoutHandler(clear);
    // On a cold start the access token is gone but the refresh cookie may not
    // be — try to pick the session back up before showing the login screen.
    (async () => {
      if (!localStorage.getItem(SESSION_MARK)) {
        setReady(true);
        return;
      }
      try {
        const body = await api.post<AuthResponse>("/api/auth/refresh");
        setAccessToken(body.access_token);
        await refreshMe();
      } catch {
        clear();
      } finally {
        setReady(true);
      }
    })();
  }, [clear, refreshMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const body = await api.post<AuthResponse>("/api/auth/login", { email, password });
      setAccessToken(body.access_token);
      localStorage.setItem(SESSION_MARK, "1");
      setUser(body.user);
      await refreshMe();
    },
    [refreshMe],
  );

  const register = useCallback(
    async (payload: { email: string; password: string; display_name: string; invite_code: string }) => {
      const body = await api.post<AuthResponse>("/api/auth/register", {
        ...payload,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Warsaw",
      });
      setAccessToken(body.access_token);
      localStorage.setItem(SESSION_MARK, "1");
      setUser(body.user);
      await refreshMe();
    },
    [refreshMe],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } catch {
      /* logging out locally matters more than the server round-trip */
    }
    clear();
  }, [clear]);

  const value = useMemo(
    () => ({ user, settings, ready, login, register, logout, refreshMe }),
    [user, settings, ready, login, register, logout, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
