import { useState } from 'react';
import { CatalogError } from '../library/ReferenceCatalog';
import { LoadingWorkout, SavedSetMetrics } from './WorkoutForms';
import { PAGE_SIZE, useExerciseHistory, useSourceHistory, weightText } from './workouts';
import type { Unit } from './workouts';

export function WorkoutPagination({ offset, total, onChange, busy, label }: { offset: number; total: number; onChange: (offset: number) => void; busy: boolean; label: string }) {
  return <nav className="history-pagination" aria-label={label}><button type="button" className="secondary-button" disabled={offset === 0 || busy} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>Previous</button><span role="status">{total ? `${Math.min(offset + 1, total)}–${Math.min(offset + PAGE_SIZE, total)} of ${total}` : '0 records'}</span><button type="button" className="secondary-button" disabled={offset + PAGE_SIZE >= total || busy} onClick={() => onChange(offset + PAGE_SIZE)}>Next</button></nav>;
}
export function RevisionHistory({ sessionId }: { sessionId: string }) {
  const [offset, setOffset] = useState(0);
  const history = useSourceHistory(sessionId, offset);
  return <section className="workout-history" aria-label="Immutable session revision history"><h3>Revision history</h3><p>Every creation, correction, completion, and deletion is preserved. These source snapshots are read-only, including after a session is deleted.</p>
    {history.isPending ? <LoadingWorkout label="Loading revisions…" /> : history.isError ? <CatalogError error={history.error} retry={() => void history.refetch()} /> : <><ol className="workout-revisions">{history.data.items.map((record) => <li key={record.id}><details><summary>Revision {record.revision} · {record.entity_type} · {record.action}<span className="measurement-note"> {new Date(record.created_at).toLocaleString()}</span></summary><p className="measurement-note">Record {record.id} · entity {record.entity_id}</p><pre className="workout-source">{JSON.stringify(record.payload, null, 2)}</pre></details></li>)}</ol>{history.data.items.length === 0 && <p>No revisions on this page. Return to the previous page.</p>}<WorkoutPagination offset={offset} total={history.data.total} onChange={setOffset} busy={history.isFetching} label="Revision history pages" /></>}
  </section>;
}
export function ExerciseHistory({ exerciseId, name, unit, onClose }: { exerciseId: string; name: string; unit: Unit; onClose: () => void }) {
  const [offset, setOffset] = useState(0);
  const history = useExerciseHistory(exerciseId, offset);
  return <section className="connection-card workout-history" aria-label={`${name} set history`}><div className="workout-section-heading"><h3>{name} · set history</h3><button type="button" className="secondary-button" onClick={onClose}>Close history</button></div><p>Current saved sets across your sessions. Corrections and removed sets remain in each session’s revision history.</p>
    {history.isPending ? <LoadingWorkout label="Loading exercise history…" /> : history.isError ? <CatalogError error={history.error} retry={() => void history.refetch()} /> : <><ul className="workout-set-list">{history.data.items.map((entry) => <li className="workout-set" key={entry.set.id}><h4>{entry.performed_on} · set {entry.set.ordinal} · {entry.set.set_type.replaceAll('_', ' ')}</h4><p>{weightText(entry.set.external_load_kg, unit)} added · {entry.set.duration_seconds === null ? `${entry.set.repetitions} reps` : `${entry.set.duration_seconds} seconds`} · RPE {entry.set.rpe ?? 'not recorded'} · RIR {entry.set.rir ?? 'not recorded'} · {entry.set.rest_seconds}s rest</p><SavedSetMetrics set={entry.set} unit={unit} /></li>)}</ul>{history.data.items.length === 0 && <p>No saved sets on this page. Log a set or return to the previous page.</p>}<WorkoutPagination offset={offset} total={history.data.total} onChange={setOffset} busy={history.isFetching} label="Exercise history pages" /></>}
  </section>;
}
