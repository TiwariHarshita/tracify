import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api, readableError } from '../lib/api';
import { Feedback } from '../components/Feedback';

export function RecoveryPage({ verify = false }: { verify?: boolean }) {
  const location = useLocation();
  const initialEmail: unknown = location.state?.email;
  const registered = verify && location.state?.registered === true;
  const [email, setEmail] = useState(typeof initialEmail === 'string' ? initialEmail : '');
  const [message, setMessage] = useState(registered ? 'Your account is created. Check your inbox for a verification link before signing in.' : '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = verify ? await api.resendVerification(email.trim()) : await api.forgotPassword(email.trim());
      setMessage(result.message);
    } catch (cause) { setError(readableError(cause)); }
    finally { setBusy(false); }
  }
  return <>
    <span className="eyebrow">{verify ? 'One more step' : 'Get back to your workspace'}</span>
    <h1>{verify ? 'Check your email' : 'Forgot your password?'}</h1>
    <p className="form-intro">{verify ? 'Open the verification link in your email, then return here to sign in.' : 'Enter the email you used for your account. We will send a reset link if it has a password.'}</p>
    {message && <Feedback success>{message}</Feedback>}
    {error && <Feedback>{error}</Feedback>}
    <form onSubmit={submit} aria-busy={busy}>
      <div className="field"><label htmlFor="email">Email address</label><input id="email" name="email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy} placeholder="you@example.com" /></div>
      <button className="button primary full" disabled={busy}>{busy ? 'Sending request…' : verify ? 'Resend verification link' : 'Send reset link'}</button>
    </form>
    <p className="recovery-note">{verify ? 'Verification links expire after 24 hours.' : 'Reset links expire after 30 minutes. For Google or GitHub accounts, use the original sign-in method.'}</p>
    <p className="switch-form"><Link to="/login">← Back to sign in</Link></p>
  </>;
}
