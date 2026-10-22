import { useAuth } from '../auth/AuthContext';

export function AccountPage() {
  const { user } = useAuth();
  return <section className="workspace-page">
    <span className="eyebrow">Your account</span><h1>A little about you.</h1><p className="page-description">The account connected to this workspace.</p>
    <div className="account-card"><h2>Profile</h2><dl>
      <div><dt>Name</dt><dd>{user?.name}</dd></div>
      <div><dt>Email address</dt><dd>{user?.email}</dd></div>
      <div><dt>Email status</dt><dd><span className="verified-label"><span className="status-dot" />Verified</span></dd></div>
    </dl><p className="account-note">To sign out, open your account menu in the top right.</p></div>
  </section>;
}
