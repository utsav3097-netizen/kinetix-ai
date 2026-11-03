import { useState } from 'react';
import type { FormEvent } from 'react';
import { failureMessage } from '../nutrition/nutrition';
import { Field } from '../workouts/WorkoutForms';
import { fromKg, toKg } from '../workouts/workouts';
import type { Unit } from '../workouts/workouts';
import { usePlanningMutation } from './plans';
import type { DraftView, PlanData, PlanEditInput } from './plans';

export function PlanEditor({ draftId, data, unit, onSaved, onCancel }: { draftId: string; data: PlanData; unit: Unit; onSaved: (draft: DraftView) => void; onCancel: () => void }) {
  const save = usePlanningMutation<DraftView>();
  const [validation, setValidation] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation(null);
    const form = new FormData(event.currentTarget);
    const value = (key: string) => Number(form.get(key));
    const input: PlanEditInput = { title: String(form.get('title')).trim(), days: data.days.map((day, dayIndex) => ({
      date: day.date, training_day: day.training_day, label: day.label,
      protein_g: value(`${dayIndex}-protein`), carbs_g: value(`${dayIndex}-carbs`), fat_g: value(`${dayIndex}-fat`),
      exercises: day.exercises.map((exercise, index) => {
        const prefix = `${dayIndex}-${index}`;
        return { exercise_id: exercise.exercise_id, sets: value(`${prefix}-sets`), external_load_kg: toKg(value(`${prefix}-load`), unit), rest_seconds: value(`${prefix}-rest`), target_min_reps: exercise.duration_seconds === null ? value(`${prefix}-min`) : null, target_max_reps: exercise.duration_seconds === null ? value(`${prefix}-max`) : null, duration_seconds: exercise.duration_seconds === null ? null : value(`${prefix}-duration`) };
      }),
    })) };
    if (input.days.some((day) => day.exercises.some((exercise) => exercise.target_min_reps !== null && exercise.target_max_reps !== null && exercise.target_min_reps > exercise.target_max_reps))) {
      setValidation('Minimum repetitions cannot exceed maximum repetitions.');
      return;
    }
    try {
      const result = await save.mutateAsync({ path: `/plans/drafts/${encodeURIComponent(draftId)}/edit`, input });
      onSaved(result);
    } catch { /* The server validation error is shown below. */ }
  }
  return <form className="connection-card planning-editor" onSubmit={(event) => void submit(event)}><h2>Edit into a new draft</h2><p>The source draft and all accepted versions remain unchanged. Dates and exercises stay fixed; generate a new plan to choose a different path or date. Calories and real-food sample portions are recomputed by the server after saving. Review the new draft before accepting it.</p><fieldset className="reference-fields" disabled={save.isPending}><legend className="visually-hidden">New draft prescriptions</legend><Field label="Plan title"><input name="title" defaultValue={data.title} maxLength={120} required pattern=".*\S.*" /></Field>{data.days.map((day, dayIndex) => <fieldset key={day.date} className="planning-edit-day"><legend>{day.date} · {day.label}</legend><div className="planning-form-grid">{(['protein', 'carbs', 'fat'] as const).map((macro) => <Field key={macro} label={`${macro === 'protein' ? 'Protein' : macro === 'carbs' ? 'Carbohydrates' : 'Fat'} (g)`}><input type="number" inputMode="decimal" name={`${dayIndex}-${macro}`} defaultValue={day.targets[`${macro}_g`]} min={0.01} step="any" required /></Field>)}</div>{day.exercises.map((exercise, index) => {
    const prefix = `${dayIndex}-${index}`;
    return <fieldset className="planning-edit-exercise" key={`${exercise.exercise_id}-${index}`}><legend>{exercise.exercise_snapshot.name}</legend><div className="planning-form-grid"><Field label="Working sets"><input type="number" name={`${prefix}-sets`} defaultValue={exercise.sets} min={1} step={1} required /></Field><Field label={`External / added load (${unit})`} hint="Effective load is recomputed from the saved baseline."><input type="number" inputMode="decimal" name={`${prefix}-load`} defaultValue={fromKg(exercise.external_load_kg, unit)} min={0} step="any" required /></Field>{exercise.duration_seconds === null ? <><Field label="Minimum reps"><input type="number" name={`${prefix}-min`} defaultValue={exercise.target_min_reps ?? undefined} min={1} step={1} required /></Field><Field label="Maximum reps"><input type="number" name={`${prefix}-max`} defaultValue={exercise.target_max_reps ?? undefined} min={1} step={1} required /></Field></> : <Field label="Hold duration (seconds)"><input type="number" name={`${prefix}-duration`} defaultValue={exercise.duration_seconds} min={1} step={1} required /></Field>}<Field label="Rest (seconds)"><input type="number" name={`${prefix}-rest`} defaultValue={exercise.rest_seconds} min={0} step={1} required /></Field></div></fieldset>;
  })}</fieldset>)}<div className="session-actions"><button type="submit" className="primary-button">{save.isPending ? 'Creating new draft…' : 'Save as new draft'}</button><button type="button" className="secondary-button" onClick={onCancel}>Cancel edit</button></div></fieldset>{validation && <div className="error-notice" role="alert">{validation}</div>}{save.error && <div className="error-notice" role="alert">{failureMessage(save.error)}</div>}</form>;
}
