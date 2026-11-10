import { Navigate, Outlet } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useProfile } from './profile';

export function ProfileRequestState({ error, retry }: { error?: Error | null; retry: () => void }) {
  return (
    <main id="main-content" className="session-loading" aria-busy={!error}>
      <h1>{error ? 'Profile unavailable.' : 'Loading your profile.'}</h1>
      {error ? <>
        <p role="alert">{error.message}</p>
        <button type="button" className="primary-button retry-session" onClick={retry}>Try again</button>
      </> : <p role="status">Getting your athlete details…</p>}
    </main>
  );
}

/** Nest tracking and planning routes inside this authenticated navigation boundary. */
export function RequireOnboarding({ children }: { children?: ReactNode } = {}) {
  const profile = useProfile();
  if (profile.isPending || profile.isError) {
    return <ProfileRequestState error={profile.error} retry={() => void profile.refetch()} />;
  }
  return profile.data.onboarding_complete && profile.data.profile
    ? <>{children ?? <Outlet />}</>
    : <Navigate to="/onboarding" replace />;
}
