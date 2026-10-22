import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { readableError } from '../lib/api';
import { Brand } from './Brand';
import { Feedback } from './Feedback';

export function AppShell() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  useEffect(() => { setOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!menu.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);
  async function logout() {
    setBusy(true); setError('');
    try { await signOut(); }
    catch (cause) { setError(readableError(cause)); }
    finally { setBusy(false); }
  }
  const initial = user?.name.trim().charAt(0).toUpperCase() || 'T';
  return <div className="workspace-layout">
    <aside className="sidebar"><Brand to="/app" /><div className="workspace-identity"><span className="workspace-avatar">{initial}</span><div>Personal workspace<small>Only you</small></div></div>
      <span className="nav-heading">WORKSPACE</span>
      <nav aria-label="Workspace"><NavLink to="/app" end className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}><span aria-hidden="true">▦</span>Overview</NavLink>
        <NavLink to="/app/account" className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}><span aria-hidden="true">◯</span>My account</NavLink></nav>
      <div className="sidebar-note"><span className="brand-dot">✦</span><strong>Follow the numbers.</strong><p>Clear reports start with knowing where every result comes from.</p></div>
      <div className="sidebar-user"><span className="avatar">{initial}</span><div>{user?.name}<small>Personal account</small></div></div>
    </aside>
    <div className="workspace-main">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span aria-hidden="true">/</span><strong>{location.pathname.endsWith('account') ? 'My account' : 'Overview'}</strong></div>
        <div className="account-menu" ref={menu}>
          <button className="account-trigger" ref={trigger} aria-expanded={open} aria-controls="account-popover" onClick={() => setOpen(previous => !previous)}>
            <span className="avatar">{initial}</span><span className="account-trigger-name">{user?.name}</span><span aria-hidden="true">⌄</span>
          </button>
          {open && <div className="account-popover" id="account-popover"><div className="popover-identity"><strong>{user?.name}</strong><span>{user?.email}</span></div>
            <Link to="/app/account">My account</Link><button onClick={() => void logout()} disabled={busy}>{busy ? 'Signing out…' : 'Sign out'}</button>
            {error && <Feedback>{error}</Feedback>}
          </div>}
        </div>
      </header>
      <Outlet />
    </div>
  </div>;
}
