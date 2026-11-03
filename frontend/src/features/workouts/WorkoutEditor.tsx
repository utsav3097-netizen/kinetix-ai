import { useState } from 'react';
import { WorkoutInsight } from '../ai/InsightCard';
import { CatalogError, ExerciseSearchPicker } from '../library/ReferenceCatalog';
import { ExerciseForm } from '../library/ReferenceForms';
import type { Exercise } from '../library/reference';
import { BlockForm, LoadingWorkout, MutationError, SavedSetMetrics, SessionForm, SetForm } from './WorkoutForms';
import { ExerciseHistory, RevisionHistory } from './WorkoutHistory';
import { blockPath, numberText, sessionPath, useSession, useWorkoutMutation, weightText } from './workouts';
import type { BlockView, SessionView, SetView, Unit } from './workouts';

function ExerciseBlock({ session, block, unit }: { session: SessionView; block: BlockView; unit: Unit }) {
  const [editing, setEditing] = useState(false);
  const [setEditor, setSetEditor] = useState<SetView | 'new' | null>(null);
  const [history, setHistory] = useState(false);
  const mutation = useWorkoutMutation();
  async function removeSet(set: SetView) {
    if (!window.confirm(`Remove set ${set.ordinal} from current totals? Its original values and this deletion remain in revision history.`)) return;
    try { await mutation.mutateAsync({ path: `${blockPath(session.id, block.id)}/sets/${encodeURIComponent(set.id)}`, method: 'DELETE' }); if (setEditor !== 'new' && setEditor?.id === set.id) setSetEditor(null); } catch { /* Rendered below. */ }
  }
  async function removeBlock() {
    if (!window.confirm(`Remove ${block.exercise_snapshot.name} and its ${block.sets.length} sets from current totals? All source records remain in session revision history.`)) return;
    try { await mutation.mutateAsync({ path: blockPath(session.id, block.id), method: 'DELETE' }); } catch { /* Rendered below. */ }
  }
  async function complete() {
    try { await mutation.mutateAsync({ path: `${blockPath(session.id, block.id)}/complete`, method: 'POST' }); } catch { /* Rendered below. */ }
  }
  return <article className="connection-card workout-block" aria-label={`${block.ordinal}. ${block.exercise_snapshot.name}`}><div className="workout-section-heading"><div><span className="eyebrow">EXERCISE {block.ordinal} · {block.completed ? 'COMPLETED' : 'IN PROGRESS'}</span><h3>{block.exercise_snapshot.name}</h3><p>{block.exercise_snapshot.equipment} · {block.exercise_snapshot.measurement_type === 'seconds' ? 'Timed holds' : `Target ${block.target_min_reps}–${block.target_max_reps} reps`} · saved bodyweight fraction {block.exercise_snapshot.biomechanical_multiplier}</p></div><div className="session-actions"><button type="button" className="text-button" disabled={mutation.isPending || editing} onClick={() => setEditing(true)}>Edit exercise</button><button type="button" className="text-button danger-text" disabled={mutation.isPending} onClick={() => void removeBlock()}>Remove exercise</button></div></div>
    {editing && <BlockForm sessionId={session.id} block={block} nextOrdinal={block.ordinal} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />}
    {block.sets.length === 0 ? <p className="catalog-state">No sets yet. Log repetitions or a timed hold below.</p> : <ol className="workout-set-list">{[...block.sets].sort((a, b) => a.ordinal - b.ordinal).map((set) => <li className="workout-set" key={set.id}><div className="workout-section-heading"><h4>Set {set.ordinal} · {set.set_type.replaceAll('_', ' ')}</h4><div className="session-actions"><button type="button" className="text-button" disabled={mutation.isPending || setEditor !== null} onClick={() => setSetEditor(set)}>Edit<span className="visually-hidden"> set {set.ordinal}</span></button><button type="button" className="text-button danger-text" disabled={mutation.isPending} onClick={() => void removeSet(set)}>Remove<span className="visually-hidden"> set {set.ordinal}</span></button></div></div><p>{weightText(set.external_load_kg, unit)} added · {set.duration_seconds === null ? `${set.repetitions} reps` : `${set.duration_seconds}s hold`} · RPE {set.rpe ?? 'not recorded'} · RIR {set.rir ?? 'not recorded'} · {set.rest_seconds}s rest</p><SavedSetMetrics set={set} unit={unit} />{set.set_type === 'warmup' && <p className="measurement-note">Warmup: excluded from hard-set volume and progression.</p>}<WorkoutInsight insightId={set.insight_id} sourceKey={set.source_record_id} analyzePath={`${blockPath(session.id, block.id)}/sets/${encodeURIComponent(set.id)}/analyze`} title={`Set ${set.ordinal} · AI analysis`} unit={unit} /></li>)}</ol>}
    {setEditor !== null && <SetForm key={setEditor === 'new' ? 'new' : setEditor.id} session={session} block={block} set={setEditor === 'new' ? undefined : setEditor} initialUnit={unit} onSaved={() => setSetEditor(null)} onCancel={() => setSetEditor(null)} />}
    <div className="workout-progression" role="status"><h4>Deterministic progression · {block.progression.state.replaceAll('_', ' ')}</h4><p>{block.progression.reason}</p>{block.progression.state !== 'insufficient_data' && <p>Next external load: <strong>{weightText(block.progression.next_weight_kg, unit)}</strong> · target {block.progression.target_reps} reps</p>}{block.progression.recovery_check && <p className="workout-warning">Review sleep, soreness, and recovery before progressing.</p>}</div>
    {block.completed && <WorkoutInsight insightId={block.insight_id} sourceKey={`${block.id}-${session.revision}`} analyzePath={`${blockPath(session.id, block.id)}/analyze`} title="Completed exercise · AI analysis" unit={unit} />}
    <MutationError error={mutation.error} /><div className="session-actions"><button className="primary-button" type="button" disabled={setEditor !== null || mutation.isPending} onClick={() => setSetEditor('new')}>Log set</button><button className="secondary-button" type="button" disabled={block.completed || mutation.isPending || setEditor !== null || editing} onClick={() => void complete()}>{block.completed ? 'Exercise completed' : 'Complete exercise'}</button><button className="text-button" type="button" onClick={() => setHistory(!history)}>{history ? 'Hide' : 'View'} exercise history</button></div>
    {history && <ExerciseHistory exerciseId={block.exercise_id} name={block.exercise_snapshot.name} unit={unit} onClose={() => setHistory(false)} />}
  </article>;
}

export function WorkoutEditor({ sessionId, unit, onDeleted, onClose }: { sessionId: string; unit: Unit; onDeleted: (id: string) => void; onClose: () => void }) {
  const query = useSession(sessionId);
  const mutation = useWorkoutMutation();
  const [editing, setEditing] = useState(false);
  const [picker, setPicker] = useState(false);
  const [custom, setCustom] = useState(false);
  const [selected, setSelected] = useState<Exercise | null>(null);
  const [history, setHistory] = useState(false);
  async function remove() {
    if (!window.confirm('Delete this session from current workouts and analytics? All session, exercise, and set source records remain available in revision history.')) return;
    try { await mutation.mutateAsync({ path: sessionPath(sessionId), method: 'DELETE' }); onDeleted(sessionId); } catch { /* Rendered below. */ }
  }
  if (query.isPending) return <LoadingWorkout label="Loading session…" />;
  if (query.isError) return <section className="connection-card"><CatalogError error={query.error} retry={() => void query.refetch()} /><button type="button" className="secondary-button" onClick={onClose}>Close session</button><RevisionHistory sessionId={sessionId} /></section>;
  const session = query.data;
  return <section className="workout-editor" aria-labelledby="workout-session-heading"><div className="connection-card"><div className="workout-section-heading"><div><span className="eyebrow">{session.performed_on} · REVISION {session.revision}</span><h2 id="workout-session-heading">{session.title}</h2></div><button type="button" className="secondary-button" onClick={onClose}>Close session</button></div><dl className="catalog-metrics workout-metrics"><div><dt>Bodyweight snapshot</dt><dd>{weightText(session.bodyweight_kg, unit)}</dd></div><div><dt>Hard-set rep-volume</dt><dd>{numberText(session.total_volume_kg)} kg·reps</dd></div><div><dt>Logged sets</dt><dd>{session.set_count}</dd></div><div><dt>Sleep</dt><dd>{session.sleep_hours === null ? 'Not reported' : `${session.sleep_hours} hours`}</dd></div><div><dt>Soreness</dt><dd>{session.soreness === null ? 'Not reported' : `${session.soreness} / 10`}</dd></div></dl><p className="measurement-note">Corrections update current views, never erase original source records. Reference-library edits do not change saved exercise snapshots or set metrics.</p><div className="session-actions"><button type="button" className="secondary-button" disabled={editing || mutation.isPending} onClick={() => setEditing(true)}>Edit session</button><button type="button" className="text-button" onClick={() => setHistory(!history)}>{history ? 'Hide' : 'View'} revision history</button><button type="button" className="text-button danger-text" disabled={mutation.isPending} onClick={() => void remove()}>Delete session</button></div><MutationError error={mutation.error} />
      {editing && <SessionForm session={session} initialWeight={session.bodyweight_kg} initialUnit={unit} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />}
      {history && <RevisionHistory sessionId={sessionId} />}
    </div>
    {[...session.exercises].sort((a, b) => a.ordinal - b.ordinal).map((block) => <ExerciseBlock key={block.id} session={session} block={block} unit={unit} />)}
    <section className="connection-card"><h3>Add an exercise</h3>{session.exercises.length === 0 && <p>Your session is ready. Select a global or private custom exercise, then log its sets.</p>}<div className="session-actions"><button type="button" className="secondary-button" onClick={() => setPicker(!picker)}>{picker ? 'Hide exercise search' : 'Search exercise library'}</button><button type="button" className="secondary-button" disabled={custom} onClick={() => setCustom(true)}>Create custom exercise</button></div>{custom && <ExerciseForm onSaved={() => { setCustom(false); setPicker(true); }} onCancel={() => setCustom(false)} />}{selected && <BlockForm key={selected.id} sessionId={sessionId} exercise={selected} nextOrdinal={Math.max(0, ...session.exercises.map((block) => block.ordinal)) + 1} onSaved={() => { setSelected(null); setPicker(false); }} onCancel={() => setSelected(null)} />}{picker && <ExerciseSearchPicker disabled={selected !== null} onSelect={setSelected} />}</section>
  </section>;
}
