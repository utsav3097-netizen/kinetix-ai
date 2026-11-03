import { useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowLeft, ArrowRight, Check } from 'lucide-react';
import { useForm } from 'react-hook-form';
import type { FieldErrors } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { ProfileRequestState } from './RequireOnboarding';
import { formatWeight, phaseLabels, profileSchema, useProfile, useSaveProfile } from './profile';
import type { Profile, ProfileInput } from './profile';

const steps: { title: string; fields: (keyof ProfileInput)[] }[] = [
  { title: 'Identity', fields: ['full_name', 'nickname', 'age', 'biological_sex'] },
  { title: 'Measurements', fields: ['height_cm', 'starting_weight_kg', 'current_weight_kg', 'body_fat_percentage', 'display_unit'] },
  { title: 'Goals', fields: ['activity_multiplier', 'phase', 'analysis_weeks'] },
];

function Field({ name, label, hint, errors, children }: {
  name: keyof ProfileInput; label: string; hint?: string; errors: FieldErrors<ProfileInput>; children: ReactNode;
}) {
  return <div className="form-field">
    <label htmlFor={name}>{label}</label>
    {children}
    {hint && <span className="field-hint" id={`${name}-hint`}>{hint}</span>}
    {errors[name] && <span className="field-error" id={`${name}-error`} role="alert">{errors[name]?.message}</span>}
  </div>;
}

export function OnboardingPage() {
  const query = useProfile();
  const { user } = useAuth();
  if (query.isPending || query.isError) return <ProfileRequestState error={query.error} retry={() => void query.refetch()} />;
  return <OnboardingForm key={user?.id} profile={query.data.profile} />;
}

function OnboardingForm({ profile }: { profile: Profile | null }) {
  const navigate = useNavigate();
  const save = useSaveProfile();
  const [step, setStep] = useState(0);
  const [serverError, setServerError] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const { register, handleSubmit, trigger, watch, setError, setValue, formState: { errors, isSubmitting } } = useForm<ProfileInput>({
    resolver: zodResolver(profileSchema),
    defaultValues: profile ?? { full_name: '', nickname: '', body_fat_percentage: null, display_unit: 'kg', phase: 'baseline_assessment', analysis_weeks: 1 },
  });
  useEffect(() => { heading.current?.focus(); }, [step]);
  // A newly recorded measurement in another view must not be overwritten by a profile edit.
  useEffect(() => {
    if (profile) setValue('current_weight_kg', profile.current_weight_kg);
  }, [profile, setValue]);
  const unit = watch('display_unit');
  const height = watch('height_cm');
  const starting = watch('starting_weight_kg');
  const current = watch('current_weight_kg');
  const fieldProps = (name: keyof ProfileInput) => ({
    id: name,
    'aria-invalid': Boolean(errors[name]),
    'aria-describedby': `${name}-hint${errors[name] ? ` ${name}-error` : ''}`,
  });
  const finish = handleSubmit(async (values) => {
    setServerError(null);
    try {
      await save.mutateAsync(values);
      navigate('/', { replace: true });
    } catch (failure) {
      setServerError(failure instanceof Error ? failure.message : 'Your profile could not be saved. Please try again.');
      if (failure instanceof ApiError) {
        let firstStep = 2;
        steps.forEach((item, index) => item.fields.forEach((name) => {
          if (failure.fieldErrors[name]) {
            setError(name, { message: failure.fieldErrors[name] });
            firstStep = Math.min(firstStep, index);
          }
        }));
        setStep(firstStep);
      }
    }
  }, (invalid) => {
    const invalidStep = steps.findIndex((item) => item.fields.some((name) => invalid[name]));
    if (invalidStep >= 0) setStep(invalidStep);
  });
  async function advance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === 2) { await finish(event); return; }
    if (await trigger(steps[step].fields, { shouldFocus: true })) setStep((value) => value + 1);
  }

  return <main id="main-content" className="onboarding-page">
    <section className="dashboard-intro" aria-labelledby="onboarding-heading">
      <span className="eyebrow"><span className="eyebrow-line" /> YOUR ATHLETE PROFILE</span>
      <h1 id="onboarding-heading">{profile ? 'Refine your' : 'Build your'} <span>baseline.</span></h1>
      <p className="intro-copy">Three steps to a profile that is yours. Nothing is saved until you complete all three steps. Refreshing returns to your last saved profile, or a fresh form.</p>
      {profile && <Link to="/" className="home-link"><ArrowLeft size={16} aria-hidden="true" />Back to dashboard</Link>}
    </section>
    <section className="connection-card onboarding-card" aria-labelledby="step-heading">
      <ol className="onboarding-steps" aria-label="Onboarding progress">
        {steps.map((item, index) => <li key={item.title} aria-current={step === index ? 'step' : undefined} className={index < step ? 'step-complete' : ''}>
          <span className="step-number">{index < step ? <Check size={16} aria-label="Complete" /> : index + 1}</span><span>{item.title}</span>
        </li>)}
      </ol>
      <h2 id="step-heading" ref={heading} tabIndex={-1}>Step {step + 1}: {steps[step].title}</h2>
      <p className="field-hint">All fields are required unless marked optional.</p>
      <form onSubmit={(event) => void advance(event)} noValidate aria-busy={isSubmitting} className="onboarding-form">
        {serverError && <div className="error-notice" role="alert">{serverError}</div>}
        {step === 0 && <div className="profile-fields">
          <Field name="full_name" label="Full name" errors={errors} hint="Your athlete profile name."><input {...fieldProps('full_name')} {...register('full_name')} autoComplete="name" maxLength={120} required readOnly={isSubmitting} /></Field>
          <Field name="nickname" label="Nickname" errors={errors} hint="How you would like to be greeted."><input {...fieldProps('nickname')} {...register('nickname')} autoComplete="nickname" maxLength={40} required readOnly={isSubmitting} /></Field>
          <Field name="age" label="Age" errors={errors} hint="13–100 years, in whole years."><input {...fieldProps('age')} {...register('age', { valueAsNumber: true })} type="number" inputMode="numeric" min={13} max={100} step={1} required readOnly={isSubmitting} /></Field>
          <Field name="biological_sex" label="Biological sex (for BMR)" errors={errors} hint="Used only for the sex-specific basal metabolic rate formula, not gender identity."><select {...fieldProps('biological_sex')} {...register('biological_sex')} required disabled={isSubmitting}><option value="">Select biological sex</option><option value="male">Male</option><option value="female">Female</option></select></Field>
        </div>}
        {step === 1 && <>
          <p className="measurement-note">Enter measurements in kilograms and centimeters. Your display preference changes how saved weight is shown, not how it is stored.</p>
          <div className="profile-fields">
            <Field name="display_unit" label="Preferred weight display" errors={errors} hint="Input fields stay in kg and cm."><select {...fieldProps('display_unit')} {...register('display_unit')} disabled={isSubmitting}><option value="kg">Kilograms (kg)</option><option value="lb">Pounds (lb)</option></select></Field>
            <Field name="height_cm" label="Height (cm)" errors={errors} hint={`50–250 cm.${Number.isFinite(height) ? ` Approximately ${(height / 2.54).toFixed(1)} inches.` : ''}`}><input {...fieldProps('height_cm')} {...register('height_cm', { valueAsNumber: true })} type="number" inputMode="decimal" min={50} max={250} step="any" required readOnly={isSubmitting} /></Field>
            <Field name="starting_weight_kg" label="Starting weight (kg)" errors={errors} hint={`20–500 kg. Starting baseline, not a dated measurement.${Number.isFinite(starting) ? ` Display: ${formatWeight(starting, unit)}.` : ''}`}><input {...fieldProps('starting_weight_kg')} {...register('starting_weight_kg', { valueAsNumber: true })} type="number" inputMode="decimal" min={20} max={500} step="any" required readOnly={isSubmitting} /></Field>
            <Field name="current_weight_kg" label="Current weight (kg)" errors={errors} hint={`${profile ? 'Record a dated check-in to update current weight.' : '20–500 kg. Saved as your first check-in for today (UTC).'}${Number.isFinite(current) ? ` Display: ${formatWeight(current, unit)}.` : ''}`}><input {...fieldProps('current_weight_kg')} {...register('current_weight_kg', { valueAsNumber: true })} type="number" inputMode="decimal" min={20} max={500} step="any" required readOnly={Boolean(profile) || isSubmitting} aria-disabled={Boolean(profile)} /></Field>
            <Field name="body_fat_percentage" label="Body fat percentage (optional)" errors={errors} hint="1–75%. Leave blank if unknown."><input {...fieldProps('body_fat_percentage')} {...register('body_fat_percentage', { setValueAs: (value: string | number | null | undefined) => value === '' || value == null ? null : Number(value) })} type="number" inputMode="decimal" min={1} max={75} step="any" readOnly={isSubmitting} /></Field>
          </div>
        </>}
        {step === 2 && <div className="profile-fields">
          <Field name="activity_multiplier" label="Activity multiplier" errors={errors} hint="1.2–2.4. Reference points: 1.2 sedentary, 1.55 moderately active, 1.9 very active. Choose a value reflecting your usual activity."><input {...fieldProps('activity_multiplier')} {...register('activity_multiplier', { valueAsNumber: true })} type="number" inputMode="decimal" min={1.2} max={2.4} step="any" required readOnly={isSubmitting} /></Field>
          <Field name="phase" label="Current phase" errors={errors} hint="Choose the focus of your current training and nutrition."><select {...fieldProps('phase')} {...register('phase')} required disabled={isSubmitting}>{Object.entries(phaseLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></Field>
          <Field name="analysis_weeks" label="Analysis window" errors={errors} hint="The number of weeks to consider together."><select {...fieldProps('analysis_weeks')} {...register('analysis_weeks', { valueAsNumber: true })} required disabled={isSubmitting}>{[1, 2, 3, 4].map((weeks) => <option value={weeks} key={weeks}>{weeks} {weeks === 1 ? 'week' : 'weeks'}</option>)}</select></Field>
        </div>}
        <div className="onboarding-actions">
          {step > 0 && <button type="button" className="secondary-button" disabled={isSubmitting} onClick={() => setStep((value) => value - 1)}><ArrowLeft size={17} aria-hidden="true" />Back</button>}
          <button type="submit" className="primary-button" disabled={isSubmitting}>{isSubmitting ? 'Saving profile…' : step === 2 ? 'Save profile' : 'Continue'}<ArrowRight size={17} aria-hidden="true" /></button>
        </div>
      </form>
    </section>
  </main>;
}
