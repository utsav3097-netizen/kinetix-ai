import { useAnnouncements } from './admin';

/** Athlete-safe public announcements; the server filters by schedule and exposes no admin data. */
export function Announcements() {
  const query = useAnnouncements();
  if (query.isPending) return <section className="connection-card" aria-label="Announcements"><p>Loading announcements…</p></section>;
  if (query.isError || !query.data?.items.length) return null;
  return <section className="connection-card" aria-labelledby="announcements-heading"><h2 id="announcements-heading">Announcements</h2><ul>{query.data.items.map(item => <li key={item.id}><strong>{item.title}</strong><p>{item.body}</p><time dateTime={item.starts_at}>{new Date(item.starts_at).toLocaleString()}</time></li>)}</ul></section>;
}

export default Announcements;
