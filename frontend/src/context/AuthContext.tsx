import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { login as apiLogin, logout as apiLogout } from '../api/auth';
import { setAccessToken, refreshAccessToken } from '../api/client';
import type { UserResponse } from '../types';
import apiClient from '../api/client';

interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: attempt silent refresh to restore session from httpOnly cookie
  useEffect(() => {
    (async () => {
      try {
        await refreshAccessToken();
        const res = await apiClient.get<UserResponse>('/auth/me');
        setUser(res.data);
      } catch {
        setUser(null);
        setAccessToken(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokenRes = await apiLogin({ email, password });
    setAccessToken(tokenRes.access_token);
    const res = await apiClient.get<UserResponse>('/auth/me');
    setUser(res.data);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
