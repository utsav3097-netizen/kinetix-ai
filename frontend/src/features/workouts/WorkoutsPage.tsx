import { useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { CatalogError } from '../library/ReferenceCatalog';
import { useProfile, utcToday } from '../profile/profile';
import { WorkoutAnalytics } from './WorkoutAnalytics';
import { WorkoutEditor } from './WorkoutEditor';
import { Field, LoadingWorkout, SessionForm, UnitControl } from './WorkoutForms';
import { RevisionHistory, WorkoutPagination } from './WorkoutHistory';
import { numberText, useSessions, weightText } from './workouts';
import type { Unit } from './workouts';
import '../library/library.css';
import './workouts.css';

function AthleteWorkouts({ initialUnit, bodyweight, analysisWeeks }: { initialUnit: Unit; bodyweight: number; analysisWeeks: number }) {
  const [unit, setUnit] = useState(initialUnit);
  const [offset, setOffset] = useState(0);
  const [dates, setDates] = useState({ from: '', to: '' });
  const [filters, setFilters] = useState(dates);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [deleted, setDeleted] = useState<string | null>(null);
  const sessions = useSessions(offset, filters.from, filters.to);
  return <main id="main-content" className="workouts-page"><header className="workout-section-heading"><div><span className="eyebrow"><span className="eyebrow-line" /> TRAINING LOG</span><h1>Workouts<span className="brand-accent">.</span></h1><p>Log what happened. Keep every correction. Progress from your own records.</p></div><UnitControl unit={unit} onChange={setUnit} /></header>
    <section className="connection-card" aria-labelledby="workout-list-heading"><div className="workout-section-heading"><h2 id="workout-list-heading">Your sessions</h2><button type="button" className="primary-button" disabled={creating} onClick={() => setCreating(true)}>New session</button></div>
      {creating && <SessionForm initialWeight={bodyweight} initialUnit={unit} onSaved={(session) => { setCreating(false); setSelected(session.id); setDeleted(null); setOffset(0); }} onCancel={() => setCreating(false)} />}
      <form className="catalog-filters workout-date-filters" onSubmit={(event) => { event.preventDefault(); setFilters(dates); setOffset(0); }}><Field label="From date"><input type="date" max={dates.to || utcToday()} value={dates.from} onChange={(event) => setDates({ ...dates, from: event.target.value })} /></Field><Field label="Through date"><input type="date" min={dates.from || undefined} max={utcToday()} value={dates.to} onChange={(event) => setDates({ ...dates, to: event.target.value })} /></Field><button className="secondary-button" type="submit">Filter sessions</button><button className="text-button" type="button" onClick={() => { setDates({ from: '', to: '' }); setFilters({ from: '', to: '' }); setOffset(0); }}>Clear dates</button></form>
      {sessions.isPending ? <LoadingWorkout label="Loading your sessions…" /> : sessions.isError ? <CatalogError error={sessions.error} retry={() => void sessions.refetch()} /> : <><ul className="workout-session-list">{sessions.data.items.map((session) => <li key={session.id}><div><h3>{session.title}</h3><p>{session.performed_on} · {weightText(session.bodyweight_kg, unit)} bodyweight</p><p>{session.exercise_count} exercises · {session.set_count} sets · {numberText(session.total_volume_kg)} kg·reps</p></div><button type="button" className="secondary-button" aria-pressed={selected === session.id} onClick={() => { setSelected(session.id); setDeleted(null); }}>Open<span className="visually-hidden"> {session.title} on {session.performed_on}</span></button></li>)}</ul>{sessions.data.items.length === 0 && <p className="catalog-state" role="status">No sessions on this page. Start a workout, clear your date filters, or return to the previous page.</p>}<WorkoutPagination offset={offset} total={sessions.data.total} onChange={setOffset} busy={sessions.isFetching} label="Workout session pages" /></>}
    </section>
    {selected && <WorkoutEditor key={selected} sessionId={selected} unit={unit} onClose={() => setSelected(null)} onDeleted={(id) => { setSelected(null); setDeleted(id); }} />}
    {deleted && <section className="connection-card"><div className="workout-section-heading"><h2>Session removed; source history retained</h2><button className="secondary-button" type="button" onClick={() => setDeleted(null)}>Close history</button></div><p role="status">This session no longer contributes to current totals. Its original entries, corrections, and deletion are preserved below.</p><RevisionHistory key={deleted} sessionId={deleted} /></section>}
    <WorkoutAnalytics initialWeeks={analysisWeeks} unit={unit} />
  </main>;
}

export function WorkoutsPage() {
  const { user } = useAuth();
  const profile = useProfile();
  if (profile.isPending) return <main id="main-content" className="workouts-page"><LoadingWorkout label="Loading athlete preferences…" /></main>;
  if (profile.isError) return <main id="main-content" className="workouts-page"><CatalogError error={profile.error} retry={() => void profile.refetch()} /></main>;
  if (!user || !profile.data.profile) return null;
  return <AthleteWorkouts key={user.id} initialUnit={profile.data.profile.display_unit} bodyweight={profile.data.profile.current_weight_kg} analysisWeeks={profile.data.profile.analysis_weeks} />;
}
