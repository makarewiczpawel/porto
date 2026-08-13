import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, setAccessToken, setLogoutHandler } from "@/api/client";
import { useSession } from "@/store/session";
import type { AuthResponse, Settings, User } from "@/api/types";

interface AuthValue {
  user: User | null;
  settings: Settings | null;
  ready: boolean;
  /** Wpuszczeni na podstawie zapisanego profilu, bo serwer był nieosiągalny. */
  offline: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (body: { email: string; password: string; display_name: string; invite_code: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/** Not a credential — just a marker so a first-ever visit does not fire a
 *  refresh request that is guaranteed to 401. */
const SESSION_MARK = "porto.session";

/**
 * Ostatnio znany profil: imię, strefa, ustawienia. Też **nie** jest poświadczeniem
 * — token odświeżający zostaje w ciasteczku `httpOnly`, a bez ważnego tokenu
 * żadne żądanie do serwera i tak nie przejdzie. Ten zapis służy wyłącznie temu,
 * żeby po restarcie w metrze aplikacja pokazała rozpoczętą sesję zamiast ekranu
 * logowania, którego bez sieci nie da się przejść.
 */
const PROFILE_KEY = "porto.profile.v1";

function cacheProfile(user: User, settings: Settings | null) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, settings }));
  } catch {
    /* brak miejsca w localStorage nie może wywalić logowania */
  }
}

function cachedProfile(): { user: User; settings: Settings | null } | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [ready, setReady] = useState(false);
  const [offline, setOffline] = useState(false);

  const clear = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setSettings(null);
    setOffline(false);
    localStorage.removeItem(SESSION_MARK);
    localStorage.removeItem(PROFILE_KEY);
  }, []);

  const refreshMe = useCallback(async () => {
    const me = await api.get<{ user: User; settings: Settings }>("/api/auth/me");
    setUser(me.user);
    setSettings(me.settings);
    setOffline(false);
    cacheProfile(me.user, me.settings);
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
        // Odmowa serwera to wylogowanie. Brak sieci to co innego: token
        // wróci, gdy wróci zasięg, a do tego czasu rozpoczęta sesja ma się
        // dać dokończyć.
        const profile = cachedProfile();
        if (!navigator.onLine && profile) {
          setUser(profile.user);
          setSettings(profile.settings);
          setOffline(true);
        } else {
          clear();
        }
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
    // Świadome wylogowanie kasuje też zapisaną sesję nauki — telefon bywa
    // wspólny, a kolejne konto nie ma prawa zobaczyć cudzych kart.
    // Wygaśnięcie tokenu (inna ścieżka, `clear`) jej nie rusza, bo tam
    // niewysłane odpowiedzi wciąż mają dokąd polecieć.
    useSession.getState().reset();
    clear();
  }, [clear]);

  const value = useMemo(
    () => ({ user, settings, ready, offline, login, register, logout, refreshMe }),
    [user, settings, ready, offline, login, register, logout, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
