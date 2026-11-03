import { createContext, useContext, useEffect, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, authSession } from '../../lib/api';
import type { AuthUser, Credentials } from '../../lib/api';

export type AuthContextValue = {
  user: AuthUser | null;
  /** True only while restoring the cookie-backed session at application startup. */
  loading: boolean;
  initializationError: string | null;
  retryInitialization: () => void;
  login: (credentials: Credentials) => Promise<void>;
  register: (credentials: Credentials) => Promise<void>;
  logout: () => Promise<void>;
  revokeAllSessions: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const user = useSyncExternalStore(authSession.subscribe, authSession.getUser);
  const [loading, setLoading] = useState(true);
  const [initializationError, setInitializationError] = useState<string | null>(null);
  const [initializationAttempt, setInitializationAttempt] = useState(0);

  useEffect(() => {
    let owner = authSession.getUser()?.id;
    return authSession.subscribe(() => {
      const nextOwner = authSession.getUser()?.id;
      if (owner !== nextOwner) {
        owner = nextOwner;
        queryClient.clear();
      }
    });
  }, [queryClient]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setInitializationError(null);
    queryClient.clear();
    authSession.restore()
      .catch((error: unknown) => {
        if (!active || (error instanceof ApiError && error.status === 401)) return;
        setInitializationError(error instanceof Error ? error.message : 'Your session could not be checked. Please try again.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [initializationAttempt, queryClient]);

  const value: AuthContextValue = {
    user,
    loading,
    initializationError,
    retryInitialization: () => setInitializationAttempt((attempt) => attempt + 1),
    async login(credentials) {
      await authSession.login(credentials);
      queryClient.clear();
    },
    async register(credentials) {
      await authSession.register(credentials);
      queryClient.clear();
    },
    async logout() {
      await authSession.logout();
      queryClient.clear();
    },
    async revokeAllSessions() {
      await authSession.revokeAllSessions();
      queryClient.clear();
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider.');
  return context;
}
