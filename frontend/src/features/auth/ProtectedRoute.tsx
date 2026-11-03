import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';

export function authenticatedDestination(state: unknown): string {
  const from: unknown = typeof state === 'object' && state !== null && 'from' in state ? state.from : null;
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) return '/';
  if (/^\/(login|register)(?:[/?#]|$)/.test(from)) return '/';
  return from;
}

/** This boundary is navigation UX. The API remains authoritative for permissions. */
export function ProtectedRoute() {
  const { user } = useAuth();
  const location = useLocation();
  return user
    ? <Outlet />
    : <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}${location.hash}` }} />;
}

export function AnonymousRoute() {
  const { user } = useAuth();
  const location = useLocation();
  return user ? <Navigate to={authenticatedDestination(location.state)} replace /> : <Outlet />;
}
