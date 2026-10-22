import { Outlet } from 'react-router-dom';
import { Brand } from '../components/Brand';
import { useAuth } from './AuthContext';
import { Feedback } from '../components/Feedback';

export function AuthLayout() {
  const { status, refresh } = useAuth();
  return <main className="auth-layout">
    <aside className="auth-story">
      <Brand inverse />
      <div className="story-copy"><span className="eyebrow">A little clarity goes a long way</span>
        <h1>Your data.<br />A clearer story.</h1>
        <p>Turn a spreadsheet into a report you can explain, check, and share.</p>
        <div className="story-card" aria-hidden="true"><span className="receipt-label">THE TRACE WAY</span>
          <div className="story-step"><span>01</span><strong>Start with your data</strong></div>
          <div className="story-step"><span>02</span><strong>Build your report</strong></div>
          <div className="story-step"><span>03</span><strong>See how it adds up</strong></div>
          <div className="card-footer"><i /> Every calculation has a receipt.</div>
        </div>
      </div>
      <p className="story-footer">Less guesswork. More confidence in your numbers.</p>
    </aside>
    <section className="auth-form-side"><div className="mobile-brand"><Brand /></div>
      <div className="auth-form-wrap">
        {status === 'error' && <Feedback>We could not connect to Trace. <button type="button" className="text-button" onClick={() => void refresh()}>Retry connection</button></Feedback>}
        <Outlet />
      </div>
      <p className="auth-footer">Your workspace, your data.</p>
    </section>
  </main>;
}
