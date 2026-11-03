import { useState } from 'react';
import { Link } from 'react-router-dom';
import { phaseLabels } from '../profile/profile';
import { MealComposer } from './MealComposer';
import { DeleteNutritionEntry, MacroRing, NutritionField } from './NutritionControls';
import { dayPath, driftText, failureMessage, mealPath, mealSlotLabels, numberText, scoreText, useNutritionMutation, waterPath } from './nutrition';
import type { AdherenceStatus, MealDraft, MealView, NutritionDay } from './nutrition';

export type MealEditor = MealView | 'new' | { draft: MealDraft; parseJobId: string; trainingDay: boolean } | null;
const statusLabels: Record<AdherenceStatus, string> = { below: 'Below range', within: 'Within range', above: 'Above range', unlogged: 'No meals recorded' };

function DayAdherence({ day }: { day: NutritionDay }) {
  const adherence = day.adherence;
  return <section className="connection-card" aria-labelledby="nutrition-adherence-heading"><h2 id="nutrition-adherence-heading">Recorded-intake signals</h2><p>These describe logged intake, not medical deficiencies or proof of a complete day.</p><dl className="nutrition-metrics"><div><dt>Macro adherence</dt><dd>{scoreText(adherence.macro_score)}</dd></div><div><dt>Caloric drift from saved target</dt><dd>{driftText(adherence.caloric_drift_kcal)}</dd></div><div><dt>Protein · {numberText(adherence.protein.min_g)}–{numberText(adherence.protein.max_g)} g</dt><dd>{statusLabels[adherence.protein.status]} · {scoreText(adherence.protein.score)}</dd></div>{(['calories', 'carbs', 'fat'] as const).map((key) => <div key={key}><dt>{key === 'calories' ? 'Energy' : key === 'carbs' ? 'Carbohydrate' : 'Fat'} · ±10% target range</dt><dd>{statusLabels[adherence[key].status]} · {scoreText(adherence[key].score)}</dd></div>)}</dl>
    <h3>Protein timing</h3>{adherence.protein_timing.status === 'insufficient_data' ? <p>Not enough data: record at least two protein-containing meals to assess gaps between their times.</p> : adherence.protein_timing.gaps.length === 0 ? <p>No gaps longer than five hours between logged protein-containing meals.</p> : <ul>{adherence.protein_timing.gaps.map((gap, index) => <li key={`${gap.from_time}-${index}`}>{gap.from_time}–{gap.to_time}: {numberText(gap.hours)} hours between protein-containing meals.</li>)}</ul>}<p className="measurement-note">Only recorded meal times are assessed. Wake, sleep, and overnight intervals are not inferred. Protein range uses 1.8–2.4 g/kg of the saved day’s bodyweight.</p>
  </section>;
}

function WaterLog({ day }: { day: NutritionDay }) {
  const change = useNutritionMutation();
  const [amount, setAmount] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  async function add(amountMl: number) {
    setError(null); setMessage('');
    if (!Number.isInteger(amountMl) || amountMl < 1 || amountMl > 10000) { setError('Enter a whole number from 1 to 10,000 ml.'); return; }
    try { await change.mutateAsync({ path: `${dayPath(day.date)}/water`, method: 'POST', input: { amount_ml: amountMl, training_day: day.training_day } }); setAmount(''); setMessage(`Recorded ${numberText(amountMl)} ml water.`); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  async function remove(id: string) {
    setError(null); setMessage('');
    try { await change.mutateAsync({ path: waterPath(id), method: 'DELETE' }); setMessage('Water entry removed; source history retained.'); return true; }
    catch (failure) { setError(failureMessage(failure)); return false; }
  }
  return <section className="connection-card" aria-labelledby="nutrition-water-heading"><div className="nutrition-section-heading"><h2 id="nutrition-water-heading">Water</h2><strong>{numberText(day.totals.water_ml)} ml recorded</strong></div><p>Track consumed water. No hydration goal is assumed.</p><div className="session-actions"><button type="button" className="secondary-button" disabled={change.isPending} onClick={() => void add(250)}>+250 ml</button><button type="button" className="secondary-button" disabled={change.isPending} onClick={() => void add(500)}>+500 ml</button></div><form className="nutrition-search" onSubmit={(event) => { event.preventDefault(); void add(Number(amount)); }}><NutritionField label="Custom water amount (ml)"><input type="number" inputMode="numeric" min={1} max={10000} step={1} required value={amount} disabled={change.isPending} onChange={(event) => setAmount(event.target.value)} /></NutritionField><button className="primary-button" disabled={change.isPending} type="submit">{change.isPending ? 'Saving…' : 'Add water'}</button></form>{error && <p className="error-notice" role="alert">{error}</p>}{message && <p className="success-notice" role="status">{message}</p>}
    {day.water_entries.length === 0 ? <p>No water entries for this date.</p> : <ul className="nutrition-water-list">{day.water_entries.map((entry) => <li key={entry.id}><div><strong>{numberText(entry.amount_ml)} ml</strong><span>Entry created <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time></span></div><DeleteNutritionEntry label={`Remove ${numberText(entry.amount_ml)} ml`} detail={`Remove this ${numberText(entry.amount_ml)} ml water entry from the daily total?`} pending={change.isPending} onDelete={() => remove(entry.id)} /></li>)}</ul>}
  </section>;
}

export function NutritionDayPanel({ day, editor, setEditor, onParsedSaved }: { day: NutritionDay; editor: MealEditor; setEditor: (editor: MealEditor) => void; onParsedSaved?: () => void }) {
  const change = useNutritionMutation();
  const [desiredType, setDesiredType] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  async function changeDayType() {
    setError(null); setMessage('');
    try { await change.mutateAsync({ path: dayPath(day.date), method: 'PUT', input: { training_day: desiredType ?? day.training_day } }); setDesiredType(null); setMessage('Day type and targets saved.'); }
    catch (failure) { setError(failureMessage(failure)); }
  }
  async function removeMeal(meal: MealView) {
    setError(null); setMessage('');
    try { await change.mutateAsync({ path: mealPath(meal.id), method: 'DELETE' }); setMessage(`Removed “${meal.title}” from current totals. Source history is retained.`); return true; }
    catch (failure) { setError(failureMessage(failure)); return false; }
  }
  const logged = day.meals.length > 0;
  return <>
    <section className="connection-card" aria-labelledby="nutrition-targets-heading"><h2 id="nutrition-targets-heading">{day.date} · {day.training_day ? 'Training day' : 'Rest day'}</h2><p>{day.persisted ? 'Saved day targets' : 'Provisional targets — saved with the first entry or day-type save'} · {phaseLabels[day.phase as keyof typeof phaseLabels] ?? day.phase.replaceAll('_', ' ')} · {numberText(day.bodyweight_kg)} kg bodyweight</p><p className="measurement-note">Saved targets do not change when your profile or active plan changes. Updating day type uses this day’s saved training/rest targets. {day.persisted ? '' : day.plan_version_id ? 'The initial day type follows your accepted plan.' : 'The initial day type uses your recorded workouts for this date.'}</p>
      {day.plan_version_id && <p>Targets from an accepted plan version. <Link className="home-link" to={`/plans?version=${encodeURIComponent(day.plan_version_id)}`}>View exact saved plan</Link></p>}
      <form className="nutrition-search" onSubmit={(event) => { event.preventDefault(); void changeDayType(); }}><NutritionField label="Day type"><select disabled={change.isPending || editor !== null} value={(desiredType ?? day.training_day) ? 'training' : 'rest'} onChange={(event) => setDesiredType(event.target.value === 'training')}><option value="training">Training day</option><option value="rest">Rest day</option></select></NutritionField><button className="secondary-button" type="submit" disabled={change.isPending || editor !== null || (day.persisted && (desiredType === null || desiredType === day.training_day))}>{change.isPending ? 'Saving…' : 'Save day type'}</button></form>
      {desiredType !== null && desiredType !== day.training_day && <p role="status">Day-type change is not saved. Save it before composing a meal with the new type.</p>}
      <div className="nutrition-rings"><MacroRing label="Energy" actual={day.totals.calories_kcal} target={day.targets.calories_kcal} unit="kcal" logged={logged} /><MacroRing label="Protein" actual={day.totals.protein_g} target={day.targets.protein_g} unit="g" logged={logged} /><MacroRing label="Carbohydrate" actual={day.totals.carbs_g} target={day.targets.carbs_g} unit="g" logged={logged} /><MacroRing label="Fat" actual={day.totals.fat_g} target={day.targets.fat_g} unit="g" logged={logged} /></div><p>Fiber recorded: {logged ? `${numberText(day.totals.fiber_g)} g` : 'No meals recorded'}. Protein range: {numberText(day.protein_range_g.min)}–{numberText(day.protein_range_g.max)} g.</p>{!logged && <p className="measurement-note">No meals recorded is missing intake data, not a claim of zero consumption. Water-only days do not count toward meal-recording coverage.</p>}
    </section>
    {error && <p className="error-notice" role="alert">{error}</p>}{message && <p className="success-notice" role="status">{message}</p>}
    <section className="connection-card" aria-labelledby="nutrition-meals-heading"><div className="nutrition-section-heading"><h2 id="nutrition-meals-heading">Meals</h2><button className="primary-button" type="button" disabled={editor !== null || change.isPending} onClick={() => { setEditor('new'); setMessage(''); }}>Add meal</button></div>
      {!logged ? <p>No meals logged for this date. Choose foods from your library to record your first meal.</p> : <ul className="nutrition-meal-list">{day.meals.map((meal) => <li key={meal.id}><article><div className="nutrition-section-heading"><div><h3>{meal.title}</h3><p>{mealSlotLabels[meal.slot]} · <time>{meal.time}</time></p></div><strong>{numberText(meal.totals.calories_kcal)} kcal</strong></div><p>P {numberText(meal.totals.protein_g)} g · C {numberText(meal.totals.carbs_g)} g · F {numberText(meal.totals.fat_g)} g · Fiber {numberText(meal.totals.fiber_g)} g</p><ul className="nutrition-saved-items">{meal.items.map((item) => <li key={item.id}><span>{item.food_snapshot.name} · {numberText(item.grams)} g consumed</span><span>{numberText(item.nutrients.calories_kcal)} kcal · P {numberText(item.nutrients.protein_g)} g · C {numberText(item.nutrients.carbs_g)} g · F {numberText(item.nutrients.fat_g)} g · Fiber {numberText(item.nutrients.fiber_g)} g</span></li>)}</ul><p className="measurement-note">Nutrients use food snapshots saved with these items.</p><div className="session-actions"><button className="secondary-button" type="button" disabled={editor !== null || change.isPending} onClick={() => { setEditor(meal); setMessage(''); }}>Edit<span className="visually-hidden"> {meal.title}</span></button><DeleteNutritionEntry label={`Delete ${meal.title}`} detail={`Remove “${meal.title}” and its items from this day’s totals?`} pending={change.isPending || editor !== null} onDelete={() => removeMeal(meal)} /></div></article></li>)}</ul>}
    </section>
    {editor !== null && <MealComposer key={editor === 'new' ? 'new' : 'draft' in editor ? `parsed-${editor.parseJobId}` : editor.id} date={day.date} trainingDay={editor !== 'new' && 'draft' in editor ? editor.trainingDay : day.training_day} meal={editor !== 'new' && !('draft' in editor) ? editor : undefined} initialDraft={editor !== 'new' && 'draft' in editor ? editor.draft : undefined} onSaved={() => { if (editor !== 'new' && 'draft' in editor) onParsedSaved?.(); setEditor(null); setMessage('Meal saved. Totals and history are updated.'); }} onCancel={() => setEditor(null)} />}
    <WaterLog day={day} /><DayAdherence day={day} />
  </>;
}
