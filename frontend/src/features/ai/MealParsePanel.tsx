import { useId, useState } from 'react';
import { NutritionField } from '../nutrition/NutritionControls';
import { mealSlotLabels } from '../nutrition/nutrition';
import type { MealDraft, MealInput } from '../nutrition/nutrition';
import { InsightCard } from './InsightCard';
import { ParsedMealReview } from './ParsedMealReview';
import { parsedMealSchema, useInsight, useRequestInsight } from './ai';

export function MealParsePanel({ date, trainingDay, jobId, editorOpen, onJobChange, onUse }: { date: string; trainingDay: boolean; jobId: string | null; editorOpen: boolean; onJobChange: (id: string | null) => void; onUse: (draft: MealDraft, date: string, trainingDay: boolean, jobId: string) => void }) {
  const heading = useId();
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [slot, setSlot] = useState<MealInput['slot']>('breakfast');
  const [time, setTime] = useState('');
  const request = useRequestInsight('nutrition');
  const query = useInsight('nutrition', jobId);
  const busy = request.isPending || (Boolean(jobId) && query.isPending) || query.data?.status === 'pending';
  const draft = query.data?.status === 'success' ? parsedMealSchema.safeParse(query.data.result) : null;
  async function parse() {
    try { const job = await request.mutateAsync({ path: '/nutrition/parse', input: { text: text.trim(), title: title.trim(), slot, time, date, training_day: trainingDay } }); onJobChange(job.id); }
    catch { /* The status card displays failures without blocking manual meals. */ }
  }
  return <section className="connection-card ai-meal-parser" aria-labelledby={heading}>
    <h2 id={heading}>Describe a meal</h2><p>Optional AI parser · {date} · {trainingDay ? 'Training day' : 'Rest day'}. Get an editable food-library draft, not an automatic log. Manual Add meal remains available if AI is unavailable.</p>
    {!jobId && <form className="reference-form" onSubmit={(event) => { event.preventDefault(); void parse(); }}><fieldset className="reference-fields" disabled={busy || editorOpen}><legend className="visually-hidden">Meal parsing request</legend>
      <div className="nutrition-form-grid"><NutritionField label="Meal title for parsing"><input value={title} required maxLength={120} onChange={(event) => setTitle(event.target.value)} /></NutritionField><NutritionField label="Meal slot for parsing"><select value={slot} onChange={(event) => setSlot(event.target.value as MealInput['slot'])}>{Object.entries(mealSlotLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></NutritionField><NutritionField label="Meal time for parsing"><input type="time" required value={time} onChange={(event) => setTime(event.target.value)} /></NutritionField></div>
      <NutritionField label="What did you eat?"><textarea value={text} required minLength={1} maxLength={2000} placeholder="For example: 150 g cooked rice and 3 eggs. Counts without measured grams will need your review." onChange={(event) => setText(event.target.value)} /></NutritionField>
      <p className="measurement-note">Only matched library foods and explicit metric amounts can be resolved automatically. Do not include personal identifiers or medical details.</p>
      <button className="primary-button" type="submit" disabled={busy || !text.trim() || !title.trim() || !time}>{request.isPending ? 'Queueing meal parse…' : 'Parse meal draft'}</button>
    </fieldset></form>}
    {(jobId || request.isPending || request.error) && <InsightCard title="Meal parser status" insight={query.data} loading={Boolean(jobId) && query.isPending} retrying={request.isPending} error={query.error ?? request.error} onRetry={query.isError ? () => void query.refetch() : undefined} />}
    {jobId && <p className="measurement-note">This job is recoverable from this page’s URL after reload. It remains private to your account. Parsing does not change daily totals.</p>}
    {draft?.success && jobId && <ParsedMealReview key={jobId} draft={draft.data} disabled={editorOpen} onUse={(edited, draftDate, draftTrainingDay) => onUse(edited, draftDate, draftTrainingDay, jobId)} />}
    {editorOpen && <p role="status">Finish or cancel the open meal composer before using another parsed draft.</p>}
    {jobId && <button className="secondary-button" type="button" disabled={editorOpen || request.isPending} onClick={() => { if (!draft?.success || window.confirm('Discard the edited draft and start another parse? No meal has been saved.')) { onJobChange(null); request.reset(); } }}>{busy ? 'Dismiss job from this page' : query.data?.status === 'unavailable' ? 'Retry with a new meal description' : 'Start another meal draft'}</button>}
  </section>;
}
