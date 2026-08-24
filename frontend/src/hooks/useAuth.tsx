import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "../api/client";

// Phase 13: real JWT auth against the backend's /api/auth endpoints, replacing Phase 1's
// in-memory stub that accepted any input. Token is kept in localStorage (api/client.ts) and
// attached to every request automatically; on first mount we validate any stored token via
// GET /me rather than trusting its mere presence (it could be expired or from a stopped
// backend that's since forgotten its state).

interface AuthContextValue {
  isAuthenticated: boolean;
  checkingSession: boolean;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setCheckingSession(false);
      return;
    }
    api
      .me()
      .then((user) => {
        setEmail(user.email);
        setIsAuthenticated(true);
      })
      .catch(() => {
        setToken(null);
      })
      .finally(() => setCheckingSession(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      checkingSession,
      email,
      login: async (loginEmail: string, password: string) => {
        const { access_token } = await api.login(loginEmail, password);
        setToken(access_token);
        setEmail(loginEmail);
        setIsAuthenticated(true);
      },
      register: async (registerEmail: string, password: string) => {
        const { access_token } = await api.register(registerEmail, password);
        setToken(access_token);
        setEmail(registerEmail);
        setIsAuthenticated(true);
      },
      logout: () => {
        setToken(null);
        setEmail(null);
        setIsAuthenticated(false);
      },
    }),
    [isAuthenticated, checkingSession, email],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
