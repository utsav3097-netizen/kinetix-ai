import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useFieldArray, useForm } from 'react-hook-form';
import { ApiError } from '../../lib/api';
import { CatalogError } from './ReferenceCatalog';
import { classificationLabels, exerciseSchema, foodSchema, useExerciseMutation, useFoodMutation, useMuscles } from './reference';
import type { Exercise, ExerciseInput, Food, FoodInput } from './reference';

function Field({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: ReactNode }) {
  return <div className="form-field"><label htmlFor={id}>{label}</label>{children}{hint && <span className="field-hint" id={`${id}-hint`}>{hint}</span>}{error && <span id={`${id}-error`} className="field-error" role="alert">{error}</span>}</div>;
}
function describe(id: string, error?: string, hint?: string) {
  return { id, 'aria-invalid': Boolean(error), 'aria-describedby': [hint ? `${id}-hint` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined };
}
function failureMessage(failure: unknown) {
  if (failure instanceof ApiError) {
    return [failure.message, ...Object.values(failure.fieldErrors)].join(' ');
  }
  return failure instanceof Error ? failure.message : 'Could not save this entry. Please try again.';
}

export function ExerciseForm({ exercise, onSaved, onCancel }: { exercise?: Exercise; onSaved: () => void; onCancel: () => void }) {
  const prefix = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const muscles = useMuscles();
  const save = useExerciseMutation();
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, control, handleSubmit, formState: { errors, isSubmitting } } = useForm<ExerciseInput>({
    resolver: zodResolver(exerciseSchema),
    defaultValues: exercise ?? { name: '', equipment: '', classification: 'upper_compound', measurement_type: 'reps', muscles: [{ muscle_id: '', contribution: 1 }] },
  });
  const { fields, append, remove } = useFieldArray({ control, name: 'muscles' });
  const submit = handleSubmit(async (input) => {
    setServerError(null);
    try { await save.mutateAsync({ action: 'save', id: exercise?.id, input }); onSaved(); }
    catch (failure) { setServerError(failureMessage(failure)); }
  });
  const numericFields = [
    { name: 'met', label: 'MET', min: 0.1, max: 30, hint: 'Metabolic equivalent: 0.1–30.' },
    { name: 'biomechanical_multiplier', label: 'Biomechanical multiplier', min: 0, max: 1, hint: 'Bodyweight fraction: 0–1. Weighted lifts: 0; pull-ups / dips: 0.95; push-ups: 0.65. Effective load = bodyweight × fraction + external kg.' },
  ] as const;
  const muscleError = errors.muscles?.root?.message ?? errors.muscles?.message;
  return <section className="connection-card reference-editor" aria-labelledby={`${prefix}-heading`}>
    <h2 id={`${prefix}-heading`} tabIndex={-1} ref={heading}>{exercise ? 'Edit custom exercise' : 'Create custom exercise'}</h2>
    <p>Custom exercises are private to your account. Global exercises cannot be changed here.</p>
    <form className="reference-form" noValidate onSubmit={(event) => void submit(event)}>
      <fieldset disabled={isSubmitting} className="reference-fields">
        <legend className="visually-hidden">Exercise details</legend>
        <div className="profile-fields">
          <Field id={`${prefix}-name`} label="Exercise name" error={errors.name?.message}><input {...describe(`${prefix}-name`, errors.name?.message)} {...register('name')} maxLength={120} required /></Field>
          <Field id={`${prefix}-equipment`} label="Equipment" error={errors.equipment?.message} hint="For example: barbell, dumbbell, or bodyweight."><input {...describe(`${prefix}-equipment`, errors.equipment?.message, 'hint')} {...register('equipment')} maxLength={80} required /></Field>
          <Field id={`${prefix}-classification`} label="Classification" error={errors.classification?.message}><select {...describe(`${prefix}-classification`, errors.classification?.message)} {...register('classification')}>{Object.entries(classificationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field id={`${prefix}-measurement`} label="Measurement" error={errors.measurement_type?.message}><select {...describe(`${prefix}-measurement`, errors.measurement_type?.message)} {...register('measurement_type')}><option value="reps">Repetitions</option><option value="seconds">Seconds (e.g. plank)</option></select></Field>
          {numericFields.map((field) => <Field key={field.name} id={`${prefix}-${field.name}`} label={field.label} error={errors[field.name]?.message} hint={field.hint}><input {...describe(`${prefix}-${field.name}`, errors[field.name]?.message, field.hint)} {...register(field.name, { valueAsNumber: true })} type="number" inputMode="decimal" min={field.min} max={field.max} step="any" required /></Field>)}
        </div>
        <fieldset className="muscle-fields" aria-describedby={`${prefix}-contribution-hint`}>
          <legend>Muscle contributions</legend>
          <p id={`${prefix}-contribution-hint`} className="measurement-note">Choose at least one unique muscle. Each contribution is 0–1; contributions do not need to add up to 1.</p>
          {muscles.isPending && <p role="status">Loading muscle options…</p>}
          {muscles.isError && <CatalogError error={muscles.error} retry={() => void muscles.refetch()} />}
          {fields.map((field, index) => <div className="muscle-row" key={field.id}>
            <Field id={`${prefix}-muscle-${field.id}`} label={`Muscle ${index + 1}`} error={errors.muscles?.[index]?.muscle_id?.message}><select {...describe(`${prefix}-muscle-${field.id}`, errors.muscles?.[index]?.muscle_id?.message)} {...register(`muscles.${index}.muscle_id`)} disabled={!muscles.data} required><option value="">Choose a muscle</option>{muscles.data?.map((muscle) => <option key={muscle.id} value={muscle.id}>{muscle.name}</option>)}</select></Field>
            <Field id={`${prefix}-contribution-${field.id}`} label={`Contribution ${index + 1}`} error={errors.muscles?.[index]?.contribution?.message}><input {...describe(`${prefix}-contribution-${field.id}`, errors.muscles?.[index]?.contribution?.message)} {...register(`muscles.${index}.contribution`, { valueAsNumber: true })} type="number" min={0} max={1} step="any" inputMode="decimal" required /></Field>
            <button className="text-button danger-text" type="button" disabled={fields.length === 1} onClick={() => remove(index)}>Remove<span className="visually-hidden"> muscle {index + 1}</span></button>
          </div>)}
          {muscleError && <p className="field-error" role="alert">{muscleError}</p>}
          <button className="secondary-button" type="button" disabled={!muscles.data || fields.length >= muscles.data.length} onClick={() => append({ muscle_id: '', contribution: 1 }, { shouldFocus: true })}>Add muscle</button>
        </fieldset>
      </fieldset>
      {serverError && <div className="error-notice" role="alert">{serverError}</div>}
      <div className="session-actions"><button className="primary-button" disabled={isSubmitting || !muscles.data} type="submit">{isSubmitting ? 'Saving…' : 'Save exercise'}</button><button className="secondary-button" type="button" disabled={isSubmitting} onClick={onCancel}>Cancel</button></div>
    </form>
  </section>;
}

export function FoodForm({ food, onSaved, onCancel }: { food?: Food; onSaved: () => void; onCancel: () => void }) {
  const prefix = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const save = useFoodMutation();
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FoodInput>({
    resolver: zodResolver(foodSchema),
    defaultValues: food ?? { name: '' },
  });
  const submit = handleSubmit(async (input) => {
    setServerError(null);
    try { await save.mutateAsync({ action: 'save', id: food?.id, input }); onSaved(); }
    catch (failure) { setServerError(failureMessage(failure)); }
  });
  const nutrients = [
    { name: 'calories', label: 'Energy (kcal)', max: 900 },
    { name: 'protein_g', label: 'Protein (g)', max: 100 },
    { name: 'carbs_g', label: 'Total carbohydrate (g)', max: 100 },
    { name: 'fat_g', label: 'Fat (g)', max: 100 },
    { name: 'fiber_g', label: 'Fiber (g)', max: 100 },
  ] as const;
  return <section className="connection-card reference-editor" aria-labelledby={`${prefix}-heading`}>
    <h2 id={`${prefix}-heading`} tabIndex={-1} ref={heading}>{food ? 'Edit custom food' : 'Create custom food'}</h2>
    <p id={`${prefix}-basis`}>Enter every nutrient per <strong>100 g</strong>, not per serving. Fiber is part of total carbohydrate. Use the food label; calories are checked against nutrients with a modest label tolerance.</p>
    <form className="reference-form" noValidate onSubmit={(event) => void submit(event)} aria-describedby={`${prefix}-basis`}>
      <fieldset disabled={isSubmitting} className="reference-fields">
        <legend className="visually-hidden">Food nutrients per 100 grams</legend>
        <div className="profile-fields">
          <Field id={`${prefix}-name`} label="Food name" error={errors.name?.message}><input {...describe(`${prefix}-name`, errors.name?.message)} {...register('name')} maxLength={120} required /></Field>
          {nutrients.map((field) => <Field key={field.name} id={`${prefix}-${field.name}`} label={`${field.label} per 100 g`} error={errors[field.name]?.message}><input {...describe(`${prefix}-${field.name}`, errors[field.name]?.message)} {...register(field.name, { valueAsNumber: true })} type="number" inputMode="decimal" min={0} max={field.max} step="any" required /></Field>)}
        </div>
      </fieldset>
      {serverError && <div className="error-notice" role="alert">{serverError}</div>}
      <div className="session-actions"><button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? 'Saving…' : 'Save food'}</button><button className="secondary-button" type="button" disabled={isSubmitting} onClick={onCancel}>Cancel</button></div>
    </form>
  </section>;
}
