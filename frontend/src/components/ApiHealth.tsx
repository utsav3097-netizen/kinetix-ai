import { useQuery } from '@tanstack/react-query';
import { Activity, ArrowUpRight, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';

async function fetchHealth({ signal }: { signal: AbortSignal }): Promise<{ status: 'ok' }> {
  const health = await api<unknown>('/health', {
    auth: false,
    signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
  });
  if (typeof health !== 'object' || health === null || !('status' in health) || health.status !== 'ok') {
    throw new Error('The backend did not report a healthy status.');
  }
  return { status: 'ok' };
}

export function ApiHealth() {
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth });
  const status = health.isFetching ? 'checking' : health.isError ? 'unavailable' : 'connected';
  const statusLabel = {
    checking: 'Checking connection',
    unavailable: 'Backend unavailable',
    connected: 'Backend connected',
  }[status];

  return (
    <section className="connection-card" aria-labelledby="connection-heading">
      <div className="card-heading">
        <span className="icon-box"><Activity size={23} aria-hidden="true" /></span>
        <span className="card-label">SYSTEM CONNECTION</span>
        <ArrowUpRight size={20} className="card-arrow" aria-hidden="true" />
      </div>
      <h2 id="connection-heading">Connected at the core.</h2>
      <p>This live check confirms the app can reach the KINETIX AI backend.</p>
      <div className={`health-state health-state--${status}`} role="status" aria-live="polite" aria-atomic="true">
        <span className="status-dot" aria-hidden="true" />
        <span>{statusLabel}</span>
      </div>
      {health.isError && !health.isFetching && (
        <p className="connection-help">The service could not be reached or is not healthy. Check that the backend and database are running, then try again.</p>
      )}
      <div className="card-footer">
        <code>/api/v1/health</code>
        <button type="button" className="refresh-button" onClick={() => void health.refetch()} disabled={health.isFetching}>
          <RefreshCw size={15} aria-hidden="true" />
          {health.isFetching ? 'Checking…' : 'Check again'}
        </button>
      </div>
    </section>
  );
}
