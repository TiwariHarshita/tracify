import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError, oauthErrorMessage, readableError } from '../lib/api';
import { Feedback } from '../components/Feedback';
import { PasswordField } from '../components/PasswordField';
import { ProviderButtons } from '../components/ProviderButtons';

export function LoginPage() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(() => oauthErrorMessage(params.get('auth_error')));
  const [unverified, setUnverified] = useState(false);
  const [busy, setBusy] = useState(false);
  const { signIn } = useAuth();
  const navigate = useNavigate();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setUnverified(false);
    try {
      await signIn({ email: email.trim(), password });
      setPassword('');
      navigate('/app', { replace: true });
    } catch (cause) {
      setError(readableError(cause));
      setUnverified(cause instanceof ApiError && cause.status === 403);
    } finally { setBusy(false); }
  }
  return <>
    <span className="eyebrow">Welcome back</span><h1>Sign in to Trace</h1>
    <p className="form-intro">Pick up where you left off.</p>
    <ProviderButtons /><div className="or-divider"><span>or use your email</span></div>
    {error && <Feedback>{error}{unverified && <><br /><Link to="/check-email" state={{ email }}>Resend verification email</Link></>}</Feedback>}
    <form onSubmit={submit} aria-busy={busy}>
      <div className="field"><label htmlFor="email">Email address</label><input id="email" name="email" type="email" autoComplete="email" required maxLength={320}
        value={email} onChange={event => setEmail(event.target.value)} disabled={busy} placeholder="you@example.com" /></div>
      <PasswordField value={password} onChange={setPassword} disabled={busy} />
      <div className="form-options"><Link to="/forgot-password">Forgot password?</Link></div>
      <button className="button primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}<span aria-hidden="true">↗</span></button>
    </form>
    <p className="switch-form">New to Trace? <Link to="/register">Create an account</Link></p>
  </>;
}
