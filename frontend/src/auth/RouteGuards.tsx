import { Navigate, Outlet } from 'react-router-dom';
import { Brand } from '../components/Brand';
import { useAuth } from './AuthContext';

export function SessionLoading() {
  return <main className="session-screen"><Brand /><span className="spinner" aria-hidden="true" />
    <p role="status">Checking your session…</p></main>;
}
export function RequireAuth() {
  const { status, refresh } = useAuth();
  if (status === 'loading') return <SessionLoading />;
  if (status === 'error') return <main className="session-screen"><Brand /><h1>We could not check your session.</h1>
    <p>Check your connection, then try again.</p><button className="button primary" onClick={() => void refresh()}>Try again</button></main>;
  return status === 'authenticated' ? <Outlet /> : <Navigate to="/login" replace />;
}
export function PublicOnly() {
  const { status } = useAuth();
  if (status === 'loading') return <SessionLoading />;
  return status === 'authenticated' ? <Navigate to="/app" replace /> : <Outlet />;
}
