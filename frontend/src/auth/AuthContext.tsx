import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api, ApiError } from '../lib/api';
import type { Credentials, User } from '../types';

type Status = 'loading' | 'authenticated' | 'anonymous' | 'error';
interface AuthState { status: Status; user: User | null }
interface AuthValue extends AuthState {
  refresh: () => Promise<void>;
  signIn: (credentials: Credentials) => Promise<void>;
  signOut: () => Promise<void>;
}
const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null });
  const generation = useRef(0);
  const mutating = useRef(false);
  const channel = useRef<BroadcastChannel | null>(null);

  const refresh = useCallback(async () => {
    if (mutating.current) return;
    const current = ++generation.current;
    try {
      const user = await api.me();
      if (generation.current === current) setState({ status: 'authenticated', user });
    } catch (error) {
      if (generation.current !== current) return;
      setState({
        status: error instanceof ApiError && error.status === 401 ? 'anonymous' : 'error',
        user: null,
      });
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onFocus = () => { void refresh(); };
    const onVisibility = () => { if (document.visibilityState === 'visible') void refresh(); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibility);
    if ('BroadcastChannel' in window) {
      channel.current = new BroadcastChannel('trace-auth');
      channel.current.onmessage = () => { void refresh(); };
    }
    return () => {
      ++generation.current;
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibility);
      channel.current?.close();
      channel.current = null;
    };
  }, [refresh]);

  const signIn = useCallback(async (credentials: Credentials) => {
    const current = ++generation.current;
    mutating.current = true;
    try {
      const user = await api.login(credentials);
      if (generation.current === current) {
        setState({ status: 'authenticated', user });
        channel.current?.postMessage('session-changed');
      }
    } finally {
      mutating.current = false;
    }
  }, []);

  const signOut = useCallback(async () => {
    ++generation.current;
    mutating.current = true;
    try {
      await api.logout();
      setState({ status: 'anonymous', user: null });
      channel.current?.postMessage('session-changed');
    } finally {
      mutating.current = false;
    }
  }, []);

  return <AuthContext.Provider value={{ ...state, refresh, signIn, signOut }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth requires AuthProvider');
  return context;
}
