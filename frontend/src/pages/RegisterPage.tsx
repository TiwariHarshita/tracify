import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, readableError } from '../lib/api';
import { Feedback } from '../components/Feedback';
import { PasswordField } from '../components/PasswordField';
import { ProviderButtons } from '../components/ProviderButtons';

export function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    if (password !== confirmation) { setError('Passwords do not match.'); return; }
    setBusy(true);
    try {
      const user = await api.register({ name: name.trim(), email: email.trim(), password });
      setPassword(''); setConfirmation('');
      navigate('/check-email', { replace: true, state: { email: user.email, registered: true } });
    } catch (cause) { setError(readableError(cause)); }
    finally { setBusy(false); }
  }
  return <>
    <span className="eyebrow">Make room for clarity</span><h1>Create your account</h1>
    <p className="form-intro">A fresh workspace for your data.</p><ProviderButtons />
    <div className="or-divider"><span>or use your email</span></div>
    {error && <Feedback>{error}</Feedback>}
    <form onSubmit={submit} aria-busy={busy}>
      <div className="field"><label htmlFor="name">Your name</label><input id="name" name="name" autoComplete="name" required maxLength={100} value={name} onChange={event => setName(event.target.value)} disabled={busy} /></div>
      <div className="field"><label htmlFor="email">Email address</label><input id="email" name="email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy} placeholder="you@example.com" /></div>
      <PasswordField value={password} onChange={setPassword} newPassword disabled={busy} />
      <div className="field"><label htmlFor="confirmation">Confirm password</label><input id="confirmation" name="confirmation" type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={busy} /></div>
      <button className="button primary full" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}<span aria-hidden="true">↗</span></button>
    </form>
    <p className="switch-form">Already have an account? <Link to="/login">Sign in</Link></p>
  </>;
}
