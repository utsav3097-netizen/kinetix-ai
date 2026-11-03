import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Activity, Pencil, Scale } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router-dom';
import { ApiError } from '../../lib/api';
import { checkInSchema, formatWeight, phaseLabels, useAddWeightCheckIn, useWeightCheckIns, utcToday } from './profile';
import type { CheckInInput, Profile } from './profile';

export function ProfileSummary({ profile }: { profile: Profile }) {
  return <section className="connection-card account-card" aria-labelledby="profile-summary-heading">
    <div className="card-heading"><span className="icon-box"><Activity size={23} aria-hidden="true" /></span><span className="card-label">ATHLETE BASELINE</span></div>
    <h2 id="profile-summary-heading">{profile.full_name}</h2>
    <dl className="account-details">
      <div><dt>Current weight</dt><dd>{formatWeight(profile.current_weight_kg, profile.display_unit)}<span className="detail-note">From your latest dated check-in</span></dd></div>
      <div><dt>Starting weight</dt><dd>{formatWeight(profile.starting_weight_kg, profile.display_unit)}</dd></div>
      <div><dt>Height / age</dt><dd>{profile.height_cm} cm / {profile.age} years</dd></div>
      <div><dt>Biological sex for BMR</dt><dd>{profile.biological_sex === 'male' ? 'Male' : 'Female'}</dd></div>
      <div><dt>Body fat</dt><dd>{profile.body_fat_percentage === null ? 'Not supplied' : `${profile.body_fat_percentage}%`}</dd></div>
      <div><dt>Phase</dt><dd>{phaseLabels[profile.phase]}</dd></div>
      <div><dt>Analysis window</dt><dd>{profile.analysis_weeks} {profile.analysis_weeks === 1 ? 'week' : 'weeks'}</dd></div>
      <div><dt>Activity multiplier</dt><dd>{profile.activity_multiplier}</dd></div>
      <div><dt>Display preference</dt><dd>{profile.display_unit === 'kg' ? 'Kilograms (kg)' : 'Pounds (lb)'}</dd></div>
    </dl>
    <Link to="/onboarding" className="secondary-button"><Pencil size={16} aria-hidden="true" />Edit profile</Link>
  </section>;
}

export function WeightCheckIns({ profile }: { profile: Profile }) {
  const pageSize = 10;
  const [offset, setOffset] = useState(0);
  const history = useWeightCheckIns(offset, pageSize);
  const add = useAddWeightCheckIn();
  const [serverError, setServerError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const { register, handleSubmit, setError, reset, watch, formState: { errors, isSubmitting } } = useForm<CheckInInput>({
    resolver: zodResolver(checkInSchema),
    defaultValues: { measured_on: utcToday() },
  });
  const enteredWeight = watch('weight_kg');
  const submit = handleSubmit(async (input) => {
    setServerError(null);
    setSuccess(null);
    try {
      await add.mutateAsync(input);
      setOffset(0);
      reset({ measured_on: utcToday() });
      setSuccess(`Saved ${formatWeight(input.weight_kg, profile.display_unit)} for ${input.measured_on}.`);
    } catch (failure) {
      setServerError(failure instanceof Error ? failure.message : 'Could not save your check-in. Please try again.');
      if (failure instanceof ApiError) {
        for (const field of ['measured_on', 'weight_kg'] as const) {
          if (failure.fieldErrors[field]) setError(field, { message: failure.fieldErrors[field] }, { shouldFocus: true });
        }
      }
    }
  });

  return <section className="connection-card account-card weight-card" aria-labelledby="weight-heading">
    <div className="card-heading"><span className="icon-box"><Scale size={23} aria-hidden="true" /></span><span className="card-label">WEIGHT CHECK-INS</span></div>
    <h2 id="weight-heading">Your weight history.</h2>
    <p>One measurement per date. Only the latest dated check-in updates your current weight. The initial profile save records today's weight (UTC).</p>
    <form className="check-in-form" onSubmit={(event) => void submit(event)} noValidate aria-busy={isSubmitting}>
      {serverError && <div className="error-notice" role="alert">{serverError}</div>}
      <div className="profile-fields">
        <div className="form-field">
          <label htmlFor="measured_on">Measurement date</label>
          <input id="measured_on" type="date" required readOnly={isSubmitting} aria-invalid={Boolean(errors.measured_on)} aria-describedby={`measurement-date-hint${errors.measured_on ? ' measured_on-error' : ''}`} {...register('measured_on')} />
          <span id="measurement-date-hint" className="field-hint">Use the date the measurement was taken.</span>
          {errors.measured_on && <span id="measured_on-error" className="field-error" role="alert">{errors.measured_on.message}</span>}
        </div>
        <div className="form-field">
          <label htmlFor="weight_kg">Weight (kg)</label>
          <input id="weight_kg" type="number" inputMode="decimal" min={20} max={500} step="any" required readOnly={isSubmitting} aria-invalid={Boolean(errors.weight_kg)} aria-describedby={`weight_kg-hint${errors.weight_kg ? ' weight_kg-error' : ''}`} {...register('weight_kg', { valueAsNumber: true })} />
          <span id="weight_kg-hint" className="field-hint">20–500 kg.{Number.isFinite(enteredWeight) ? ` Display: ${formatWeight(enteredWeight, profile.display_unit)}.` : ' Entries are always in kg.'}</span>
          {errors.weight_kg && <span id="weight_kg-error" className="field-error" role="alert">{errors.weight_kg.message}</span>}
        </div>
      </div>
      <button type="submit" className="primary-button" disabled={isSubmitting}>{isSubmitting ? 'Saving check-in…' : 'Add check-in'}</button>
      {success && <p className="success-notice" role="status">{success}</p>}
    </form>
    <div className="weight-history" aria-busy={history.isFetching}>
      <h3>Recent check-ins</h3>
      {history.isPending && <p role="status">Loading measurements…</p>}
      {history.isError && <div className="error-notice" role="alert">{history.error.message}<button type="button" className="text-button" onClick={() => void history.refetch()}>Try again</button></div>}
      {history.data && <>
        {history.data.items.length ? <table className="weight-table"><caption className="visually-hidden">Weight measurements, newest first</caption><thead><tr><th scope="col">Date</th><th scope="col">Weight ({profile.display_unit})</th></tr></thead><tbody>{history.data.items.map((item) => <tr key={item.id}><td><time dateTime={item.measured_on}>{item.measured_on}</time></td><td>{formatWeight(item.weight_kg, profile.display_unit)}</td></tr>)}</tbody></table> : <p>No check-ins on this page.</p>}
        <nav className="history-pagination" aria-label="Weight history pages">
          <button type="button" className="secondary-button" disabled={offset === 0 || history.isFetching} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}>Previous</button>
          <span role="status">{history.data.total === 0 ? '0 measurements' : `${offset + 1}–${Math.min(offset + pageSize, history.data.total)} of ${history.data.total}`}</span>
          <button type="button" className="secondary-button" disabled={offset + pageSize >= history.data.total || history.isFetching} onClick={() => setOffset((value) => value + pageSize)}>Next</button>
        </nav>
      </>}
    </div>
  </section>;
}
