import { useState } from 'react';
import { Flame } from 'lucide-react';
import { Link } from 'react-router-dom';
import { phaseLabels } from '../profile/profile';
import { useDashboardTargets } from './targets';

const formatAmount = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 });

export function TargetPanel() {
  const [trainingDay, setTrainingDay] = useState<boolean | null>(null);
  const targets = useDashboardTargets(trainingDay);
  const data = targets.data;

  return <section className="connection-card account-card" aria-labelledby="targets-heading">
    <div className="card-heading"><span className="icon-box"><Flame size={23} aria-hidden="true" /></span><span className="card-label">ENERGY & MACRO TARGETS</span></div>
    <h2 id="targets-heading">Your daily targets.</h2>
    <p>Non-medical server estimates. When today's date is covered by your active accepted plan, its saved targets take priority; otherwise targets use your profile and current weight.</p>
    <div className="form-field">
      <label htmlFor="target-day">Day type</label>
      <select id="target-day" value={trainingDay === null ? 'automatic' : trainingDay ? 'training' : 'rest'} onChange={(event) => setTrainingDay(event.target.value === 'automatic' ? null : event.target.value === 'training')} aria-describedby="target-day-hint">
        <option value="automatic">Automatic / prescribed day</option>
        <option value="training">Training day</option>
        <option value="rest">Rest day</option>
      </select>
      <span id="target-day-hint" className="field-hint">Automatic respects an active plan's prescribed day. A manual selection previews the saved training/rest targets.</span>
    </div>
    <div aria-busy={targets.isFetching} aria-live="polite">
      {targets.isPending && <p role="status">Loading {trainingDay === null ? 'prescribed' : trainingDay ? 'training' : 'rest'} day targets…</p>}
      {targets.isFetching && !targets.isPending && <p role="status">Updating targets…</p>}
      {targets.isError && <div className="error-notice" role="alert">
        <strong>Targets unavailable.</strong> {targets.error.message}
        <p>No substitute targets are shown. If the profile cannot support a valid macro allocation, review its measurements, activity level and phase.</p>
        <div className="session-actions">
          <Link to="/onboarding" className="secondary-button">Review profile</Link>
          <button type="button" className="text-button" onClick={() => void targets.refetch()} disabled={targets.isFetching}>Try again</button>
        </div>
      </div>}
      {data && !targets.isError && <>
        {data.plan_version_id && <p>Targets from your active accepted plan. <Link className="home-link" to={`/plans?version=${encodeURIComponent(data.plan_version_id)}`}>View exact version</Link></p>}
        <dl className="account-details">
          <div><dt>Phase / day</dt><dd>{phaseLabels[data.phase]} / {data.training_day ? 'Training' : 'Rest'}</dd></div>
          <div><dt>BMR</dt><dd>{formatAmount(data.bmr_kcal)} kcal/day<span className="detail-note">Estimated basal metabolic rate (Mifflin–St Jeor)</span></dd></div>
          <div><dt>TDEE</dt><dd>{formatAmount(data.tdee_kcal)} kcal/day<span className="detail-note">Estimated total daily energy expenditure at your activity level</span></dd></div>
          <div><dt>Daily calories</dt><dd>{formatAmount(data.macros.calories_kcal)} kcal<span className="detail-note">Actual energy target from this day's allocated macros</span></dd></div>
          <div><dt>Protein</dt><dd>{formatAmount(data.macros.protein_g)} g</dd></div>
          <div><dt>Carbohydrates</dt><dd>{formatAmount(data.macros.carbs_g)} g</dd></div>
          <div><dt>Fat</dt><dd>{formatAmount(data.macros.fat_g)} g</dd></div>
          <div><dt>Protein adherence range</dt><dd>{formatAmount(data.protein_range_g.min)}–{formatAmount(data.protein_range_g.max)} g/day<span className="detail-note">1.8–2.4 g per kg of current body weight</span></dd></div>
        </dl>
        {data.plan_version_id ? <p>These targets are frozen in the accepted plan. Manual macro edits can differ from the standard phase formula; existing nutrition records keep their own saved targets.</p> : data.phase === 'body_recomposition' ? <p>
          Base maintenance energy is {formatAmount(data.macros.base_calories_kcal)} kcal/day (TDEE).
          Carbohydrates are increased 10% on training days and reduced 10% on rest days; protein and fat stay unchanged.
          This {data.training_day ? 'training' : 'rest'} day's carbohydrate factor is {formatAmount(data.macros.carb_cycle_factor)}×,
          so the actual energy target is {formatAmount(data.macros.calories_kcal)} kcal, not the unchanged base maintenance amount.
        </p> : <p>Base phase energy: {formatAmount(data.macros.base_calories_kcal)} kcal/day. This phase uses the same targets on training and rest days.</p>}
        <p>{data.disclaimer}</p>
        <p className="detail-note">Displayed amounts are rounded to one decimal place. These are targets, not logged food intake.</p>
      </>}
    </div>
  </section>;
}
