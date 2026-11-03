import { useRef, useState } from 'react';
import { LogOut, ShieldCheck, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ProfileSummary, WeightCheckIns } from '../profile/ProfileDashboard';
import { useProfile } from '../profile/profile';
import { useAuth } from '../auth/AuthProvider';
import { TargetPanel } from '../dashboard/TargetPanel';

export function Dashboard() {
  const { user, logout, revokeAllSessions } = useAuth();
  const { data } = useProfile();
  const profile = data?.profile;
  const [pending, setPending] = useState<'logout' | 'revoke' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const revokeTrigger = useRef<HTMLButtonElement>(null);

  async function endSession(action: 'logout' | 'revoke') {
    setError(null);
    setPending(action);
    try {
      if (action === 'revoke') await revokeAllSessions();
      else await logout();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not end your session. Please try again.');
    } finally {
      setPending(null);
    }
  }

  if (!user || !profile) return null;

  return (
    <main id="main-content" className="dashboard">
      <section className="dashboard-intro" aria-labelledby="dashboard-heading">
        <span className="eyebrow"><span className="eyebrow-line" /> YOUR KINETIX DASHBOARD</span>
        <h1 id="dashboard-heading">Welcome, <span>{profile.nickname}.</span></h1>
        <p className="intro-copy">Your athlete baseline, daily energy targets and dated weight measurements, together in one place.</p>
        <Link to="/library" className="home-link">Browse your exercise and food library</Link>
      </section>
      <div className="account-grid">
        <TargetPanel />
        <ProfileSummary profile={profile} />
        <WeightCheckIns profile={profile} />
        <section className="connection-card account-card" aria-labelledby="account-heading">
          <div className="card-heading">
            <span className="icon-box"><UserRound size={23} aria-hidden="true" /></span>
            <span className="card-label">ACCOUNT DETAILS</span>
            <span className={`role-badge${user.role === 'admin' ? ' role-badge--admin' : ''}`}>{user.role === 'admin' ? 'ADMIN' : 'USER'}</span>
          </div>
          <h2 id="account-heading">Your identity.</h2>
          <dl className="account-details">
            <div><dt>Email address</dt><dd>{user.email}</dd></div>
            <div><dt>Account role</dt><dd>{user.role === 'admin' ? 'Administrator' : 'User'}<span className="detail-note">Assigned and enforced by the server</span></dd></div>
            <div><dt>Account ID</dt><dd className="account-id">{user.id}</dd></div>
          </dl>
          <div className="session-section" aria-labelledby="sessions-heading">
            <h3 id="sessions-heading"><ShieldCheck size={19} aria-hidden="true" /> Your sessions</h3>
            <p>Log out of this browser session, or revoke every active session for your account.</p>
            {error && <div className="error-notice" role="alert">{error}</div>}
            <div className="session-actions">
              <button type="button" className="secondary-button" onClick={() => void endSession('logout')} disabled={pending !== null}>
                <LogOut size={17} aria-hidden="true" />{pending === 'logout' ? 'Logging out…' : 'Log out'}
              </button>
              <button ref={revokeTrigger} type="button" className="text-button danger-text" onClick={() => setConfirmRevoke(true)} disabled={pending !== null} aria-expanded={confirmRevoke} aria-controls="revoke-confirmation">Sign out everywhere</button>
            </div>
            {confirmRevoke && (
              <div id="revoke-confirmation" className="revoke-confirmation" role="group" aria-labelledby="revoke-heading" aria-busy={pending === 'revoke'}>
                <h4 id="revoke-heading">Revoke all sessions?</h4>
                <p>This includes your current session. You will need to log in again on every browser or device.</p>
                <div className="session-actions">
                  <button type="button" className="danger-button" onClick={() => void endSession('revoke')} disabled={pending !== null} autoFocus>{pending === 'revoke' ? 'Revoking sessions…' : 'Revoke all sessions'}</button>
                  <button type="button" className="text-button" onClick={() => { setConfirmRevoke(false); revokeTrigger.current?.focus(); }} disabled={pending !== null}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
