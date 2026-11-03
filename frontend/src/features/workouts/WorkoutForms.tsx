import { useId, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { effectiveLoadKg } from '../../utils/fitnessAlgorithms';
import { utcToday } from '../profile/profile';
import { blockPath, fromKg, numberText, sessionPath, toKg, useWorkoutMutation, weightText } from './workouts';
import type { BlockView, SessionView, SetInput, SetView, Unit } from './workouts';

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="form-field"><span>{label}</span>{children}{hint && <span className="field-hint">{hint}</span>}</label>;
}
export function LoadingWorkout({ label = 'Loading workout records…' }: { label?: string }) {
  return <div className="workout-skeleton" role="status" aria-busy="true"><span>{label}</span><div /><div /><div /></div>;
}
export function MutationError({ error }: { error: Error | null }) {
  return error ? <div role="alert" className="error-notice">{error.message}</div> : null;
}
export function UnitControl({ unit, onChange }: { unit: Unit; onChange: (unit: Unit) => void }) {
  return <Field label="Weight unit"><select value={unit} onChange={(event) => onChange(event.target.value as Unit)}><option value="kg">Kilograms (kg)</option><option value="lb">Pounds (lb)</option></select></Field>;
}
const optional = (value: string) => value.trim() === '' ? null : Number(value);
const inputWeight = (kg: number, unit: Unit) => String(fromKg(kg, unit));

export function SessionForm({ session, initialWeight, initialUnit, onSaved, onCancel }: { session?: SessionView; initialWeight: number; initialUnit: Unit; onSaved: (session: SessionView) => void; onCancel: () => void }) {
  const [unit, setUnit] = useState(initialUnit);
  const [title, setTitle] = useState(session?.title ?? 'Training session');
  const [date, setDate] = useState(session?.performed_on ?? utcToday());
  const [weight, setWeight] = useState(inputWeight(session?.bodyweight_kg ?? initialWeight, initialUnit));
  const [sleep, setSleep] = useState(session?.sleep_hours?.toString() ?? '');
  const [soreness, setSoreness] = useState(session?.soreness?.toString() ?? '');
  const save = useWorkoutMutation();
  const lockedWeight = Boolean(session?.set_count);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (session && !window.confirm('Save this correction? The previous session details remain in revision history.')) return;
    try {
      const result = await save.mutateAsync({ path: session ? sessionPath(session.id) : '/workouts', method: session ? 'PUT' : 'POST', input: { title: title.trim(), performed_on: date, bodyweight_kg: lockedWeight && session ? session.bodyweight_kg : toKg(Number(weight), unit), sleep_hours: optional(sleep), soreness: optional(soreness) } });
      if (result) onSaved(result);
    } catch { /* The mutation error is rendered below. */ }
  }
  return <form onSubmit={(event) => void submit(event)} className="reference-form">
    <h3>{session ? 'Correct session details' : 'Start a workout'}</h3>
    <fieldset className="reference-fields" disabled={save.isPending}><legend className="visually-hidden">Session details</legend><div className="profile-fields">
      <Field label="Session title"><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} required pattern=".*\S.*" /></Field>
      <Field label="Performed on (UTC date)"><input type="date" value={date} max={utcToday()} onChange={(event) => setDate(event.target.value)} required /></Field>
      <UnitControl unit={unit} onChange={(next) => { if (weight !== '') setWeight(inputWeight(toKg(Number(weight), unit), next)); setUnit(next); }} />
      <Field label={`Bodyweight (${unit})`} hint={lockedWeight ? 'Locked after sets are logged; saved set bodyweights never change.' : 'Stored with the workout, independently of later profile changes.'}><input type="number" inputMode="decimal" min={fromKg(20, unit)} max={fromKg(500, unit)} step="any" value={weight} onChange={(event) => setWeight(event.target.value)} disabled={lockedWeight} required /></Field>
      <Field label="Sleep (hours, optional)"><input type="number" inputMode="decimal" min={0} max={24} step="any" value={sleep} onChange={(event) => setSleep(event.target.value)} /></Field>
      <Field label="Soreness (0–10, optional)"><input type="number" inputMode="decimal" min={0} max={10} step="any" value={soreness} onChange={(event) => setSoreness(event.target.value)} /></Field>
    </div></fieldset>
    <MutationError error={save.error} /><div className="session-actions"><button className="primary-button" disabled={save.isPending} type="submit">{save.isPending ? 'Saving…' : session ? 'Save correction' : 'Create session'}</button><button className="secondary-button" disabled={save.isPending} type="button" onClick={onCancel}>Cancel</button></div>
  </form>;
}

export function BlockForm({ sessionId, block, exercise, nextOrdinal, onSaved, onCancel }: { sessionId: string; block?: BlockView; exercise?: { id: string; name: string; measurement_type: 'reps' | 'seconds' }; nextOrdinal: number; onSaved: () => void; onCancel: () => void }) {
  const [ordinal, setOrdinal] = useState(String(block?.ordinal ?? nextOrdinal));
  const [minimum, setMinimum] = useState(String(block?.target_min_reps ?? 8));
  const [maximum, setMaximum] = useState(String(block?.target_max_reps ?? 10));
  const save = useWorkoutMutation();
  const timed = (block?.exercise_snapshot.measurement_type ?? exercise?.measurement_type) === 'seconds';
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (block && !window.confirm('Save this exercise correction? Previous details remain in revision history.')) return;
    try {
      await save.mutateAsync({ path: block ? blockPath(sessionId, block.id) : `${sessionPath(sessionId)}/exercises`, method: block ? 'PUT' : 'POST', input: { ordinal: Number(ordinal), target_min_reps: Number(minimum), target_max_reps: Number(maximum), ...(!block && exercise ? { exercise_id: exercise.id } : {}) } });
      onSaved();
    } catch { /* The mutation error is rendered below. */ }
  }
  return <form className="reference-form workout-inline-form" onSubmit={(event) => void submit(event)}><h4>{block ? 'Edit' : 'Add'} {block?.exercise_snapshot.name ?? exercise?.name}</h4><fieldset className="reference-fields" disabled={save.isPending}><legend className="visually-hidden">Exercise order and targets</legend><div className="profile-fields">
    <Field label="Exercise order"><input type="number" inputMode="numeric" min={1} step={1} required value={ordinal} onChange={(event) => setOrdinal(event.target.value)} /></Field>
    {!timed && <><Field label="Target minimum reps"><input type="number" inputMode="numeric" min={1} step={1} required value={minimum} onChange={(event) => setMinimum(event.target.value)} /></Field><Field label="Target maximum reps"><input type="number" inputMode="numeric" min={Number(minimum) || 1} step={1} required value={maximum} onChange={(event) => setMaximum(event.target.value)} /></Field></>}
  </div>{timed && <p className="measurement-note">Timed exercise: enter seconds in each set. Rep-based progression does not apply.</p>}</fieldset><MutationError error={save.error} /><div className="session-actions"><button type="submit" className="primary-button" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save exercise'}</button><button type="button" className="secondary-button" disabled={save.isPending} onClick={onCancel}>Cancel</button></div></form>;
}

export function SetForm({ session, block, set, initialUnit, onSaved, onCancel }: { session: SessionView; block: BlockView; set?: SetView; initialUnit: Unit; onSaved: () => void; onCancel: () => void }) {
  const hintId = useId();
  const [unit, setUnit] = useState(initialUnit);
  const [ordinal, setOrdinal] = useState(String(set?.ordinal ?? Math.max(0, ...block.sets.map((item) => item.ordinal)) + 1));
  const [kind, setKind] = useState<SetInput['set_type']>(set?.set_type ?? 'working');
  const [load, setLoad] = useState(inputWeight(set?.external_load_kg ?? 0, initialUnit));
  const [reps, setReps] = useState(set?.repetitions?.toString() ?? '8');
  const [duration, setDuration] = useState(set?.duration_seconds?.toString() ?? '30');
  const [rpe, setRpe] = useState(set?.rpe?.toString() ?? '');
  const [rir, setRir] = useState(set?.rir?.toString() ?? '');
  const [rest, setRest] = useState(String(set?.rest_seconds ?? 90));
  const [validation, setValidation] = useState('');
  const save = useWorkoutMutation();
  const timed = block.exercise_snapshot.measurement_type === 'seconds';
  const loadKg = toKg(Number(load), unit);
  const preview = load !== '' && Number.isFinite(loadKg) && loadKg >= 0 ? effectiveLoadKg(set?.bodyweight_kg ?? session.bodyweight_kg, loadKg, block.exercise_snapshot.biomechanical_multiplier) : null;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setValidation('');
    if (rpe !== '' && rir !== '' && Math.abs(Number(rpe) + Number(rir) - 10) > 0.000001) { setValidation('When both are entered, RPE must equal 10 minus RIR.'); return; }
    if (set && !window.confirm('Save this set correction? The original set and metrics remain in revision history.')) return;
    const input: SetInput = { ordinal: Number(ordinal), set_type: kind, external_load_kg: loadKg, repetitions: timed ? null : Number(reps), duration_seconds: timed ? Number(duration) : null, rpe: optional(rpe), rir: optional(rir), rest_seconds: Number(rest) };
    try {
      await save.mutateAsync({ path: `${blockPath(session.id, block.id)}/sets${set ? `/${encodeURIComponent(set.id)}` : ''}`, method: set ? 'PUT' : 'POST', input });
      onSaved();
    } catch { /* The mutation error is rendered below. */ }
  }
  return <form className="reference-form workout-inline-form" onSubmit={(event) => void submit(event)}><h4>{set ? `Edit set ${set.ordinal}` : 'Log a set'}</h4><fieldset className="reference-fields" disabled={save.isPending}><legend className="visually-hidden">Set details</legend><div className="profile-fields">
    <Field label="Set order"><input type="number" inputMode="numeric" min={1} step={1} value={ordinal} onChange={(event) => setOrdinal(event.target.value)} required /></Field>
    <Field label="Set type"><select value={kind} onChange={(event) => setKind(event.target.value as SetInput['set_type'])}><option value="warmup">Warmup</option><option value="working">Working</option><option value="drop_set">Drop set</option><option value="failure">Failure</option></select></Field>
    <UnitControl unit={unit} onChange={(next) => { if (load !== '') setLoad(inputWeight(loadKg, next)); setUnit(next); }} />
    <Field label={`External load (${unit})`} hint="Added weight only, not bodyweight."><input type="number" inputMode="decimal" min={0} max={fromKg(1000, unit)} step="any" required value={load} onChange={(event) => setLoad(event.target.value)} /></Field>
    {timed ? <Field label="Duration (seconds)"><input type="number" inputMode="numeric" min={1} max={7200} step={1} value={duration} onChange={(event) => setDuration(event.target.value)} required /></Field> : <Field label="Repetitions"><input type="number" inputMode="numeric" min={0} max={1000} step={1} value={reps} onChange={(event) => setReps(event.target.value)} required /></Field>}
    <Field label="RPE (1–10, optional)"><input type="number" inputMode="decimal" min={1} max={10} step="any" value={rpe} onChange={(event) => setRpe(event.target.value)} aria-describedby={hintId} /></Field>
    <Field label="RIR (0–9, optional)"><input type="number" inputMode="decimal" min={0} max={9} step="any" value={rir} onChange={(event) => setRir(event.target.value)} aria-describedby={hintId} /></Field>
    <Field label="Rest (seconds)"><input type="number" inputMode="numeric" min={0} max={7200} step={1} required value={rest} onChange={(event) => setRest(event.target.value)} /></Field>
  </div><p id={hintId} className="measurement-note">Working sets need at least RPE or RIR for progression. You may save without effort, but the recommendation will be insufficient data. If both are supplied, RPE + RIR must equal 10.</p>
  <p className="workout-preview" role="status">Provisional effective load: {preview === null ? 'Enter a valid external load.' : `${weightText(preview, unit)} (${numberText(preview)} kg)`}. Saved server calculations are authoritative.</p>
  {timed && <p className="measurement-note">Timed holds do not produce rep-volume or estimated 1RM.</p>}</fieldset>{validation && <p className="field-error" role="alert">{validation}</p>}<MutationError error={save.error} /><div className="session-actions"><button type="submit" className="primary-button" disabled={save.isPending}>{save.isPending ? 'Saving…' : set ? 'Save set correction' : 'Save set'}</button><button type="button" className="secondary-button" disabled={save.isPending} onClick={onCancel}>Cancel</button></div></form>;
}

export function SavedSetMetrics({ set, unit }: { set: SetView; unit: Unit }) {
  return <><dl className="catalog-metrics workout-metrics"><div><dt>Effective load</dt><dd>{weightText(set.metrics.effective_load_kg, unit)}</dd></div><div><dt>Rep-volume</dt><dd>{set.metrics.volume_kg === null ? 'Not applicable' : `${numberText(set.metrics.volume_kg)} kg·reps`}</dd></div><div><dt>Estimated 1RM</dt><dd>{set.metrics.estimated_1rm_kg === null ? 'Unavailable' : weightText(set.metrics.estimated_1rm_kg, unit)}</dd></div></dl>{set.metrics.estimate_unavailable_reason && <p className="measurement-note">{set.metrics.estimate_unavailable_reason}</p>}<p className="measurement-note">Saved server metrics · bodyweight snapshot {weightText(set.bodyweight_kg, unit)}{set.metrics.one_rm_formula ? ` · ${set.metrics.one_rm_formula}` : ''}</p></>;
}
