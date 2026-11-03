import { useId, useState } from 'react';
import { CatalogError } from '../library/ReferenceCatalog';
import type { Food } from '../library/reference';
import { CustomFoodForm } from '../nutrition/MealComposer';
import { NutritionField, NutritionLoading, NutritionPagination } from '../nutrition/NutritionControls';
import { mealSchema, mealSlotLabels, numberText, useNutritionFoods } from '../nutrition/nutrition';
import type { FoodSnapshot, MealDraft, MealInput, Nutrients } from '../nutrition/nutrition';
import type { ParsedMealDraft } from './ai';

type ReviewItem = { key: number; label: string; food_id: string | null; food_snapshot: FoodSnapshot | null; quantity: string; reason: string | null };
function DraftFoodPicker({ item, index, onChange, onRemove }: { item: ReviewItem; index: number; onChange: (item: ReviewItem) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(!item.food_id);
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [custom, setCustom] = useState(false);
  const foods = useNutritionFoods(search, offset);
  const valid = Boolean(item.food_id && item.food_snapshot && Number(item.quantity) > 0 && Number(item.quantity) <= 5000 && Number.isFinite(Number(item.quantity)));
  function select(food: Food) {
    onChange({ ...item, food_id: food.id, food_snapshot: { name: food.name, basis_grams: food.basis_grams, calories: food.calories, protein_g: food.protein_g, carbs_g: food.carbs_g, fat_g: food.fat_g, fiber_g: food.fiber_g } });
    setOpen(false);
  }
  return <li className="ai-parse-item"><h4>Item {index + 1}: {item.label}</h4>
    <p>{valid ? 'Ready for your review' : 'Unresolved — choose a food and enter consumed grams.'}</p>{item.reason && <p className="measurement-note">Parser note: {item.reason}</p>}
    <p>Selected food: <strong>{item.food_snapshot?.name ?? 'None — not guessed'}</strong></p>
    <NutritionField label={`Consumed grams — parsed item ${index + 1}`}><input type="number" inputMode="decimal" min="0" max="5000" step="any" value={item.quantity} onChange={(event) => onChange({ ...item, quantity: event.target.value })} /></NutritionField>
    <div className="session-actions"><button type="button" className="secondary-button" onClick={() => setOpen(!open)}>{open ? 'Hide food picker' : 'Choose or change food'}<span className="visually-hidden"> for item {index + 1}</span></button><button type="button" className="text-button danger-text" onClick={onRemove}>Remove item {index + 1}</button></div>
    {open && <div><form className="nutrition-search" onSubmit={(event) => { event.preventDefault(); setSearch(input.trim()); setOffset(0); }}><NutritionField label={`Search food for item ${index + 1}`}><input type="search" maxLength={120} value={input} onChange={(event) => setInput(event.target.value)} /></NutritionField><button className="secondary-button" type="submit">Search foods</button></form>
      {foods.isPending ? <NutritionLoading label="Loading food library…" /> : foods.isError ? <CatalogError error={foods.error} retry={() => void foods.refetch()} /> : <><ul className="nutrition-food-results">{foods.data.items.map((food) => <li key={food.id}><div><strong>{food.name}</strong><p>Per 100 g: {numberText(food.calories)} kcal · P {numberText(food.protein_g)} g · C {numberText(food.carbs_g)} g · F {numberText(food.fat_g)} g</p></div><button type="button" className="secondary-button" onClick={() => select(food)}>Select<span className="visually-hidden"> {food.name} for item {index + 1}</span></button></li>)}</ul>{foods.data.total === 0 && <p>No matching foods. Search another name or create a food from its label.</p>}<NutritionPagination offset={offset} total={foods.data.total} limit={10} onChange={setOffset} label={`Food options for item ${index + 1}`} /></>}
      <button className="secondary-button" type="button" disabled={custom} onClick={() => setCustom(true)}>Create custom food</button>{custom && <CustomFoodForm onSaved={() => { setCustom(false); setInput(''); setSearch(''); setOffset(0); }} onCancel={() => setCustom(false)} />}
    </div>}
  </li>;
}

export function ParsedMealReview({ draft, disabled, onUse }: { draft: ParsedMealDraft; disabled: boolean; onUse: (draft: MealDraft, date: string, trainingDay: boolean) => void }) {
  const heading = useId();
  const [title, setTitle] = useState(draft.title);
  const [slot, setSlot] = useState<MealInput['slot']>(draft.slot);
  const [time, setTime] = useState(draft.time);
  const [items, setItems] = useState<ReviewItem[]>(() => draft.items.map((item, key) => ({ key, label: item.label, food_id: item.food_id, food_snapshot: item.food_snapshot, quantity: item.grams === null ? '' : String(item.grams), reason: item.reason })));
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resolved: MealDraft['items'] = [];
  const totals: Nutrients = { calories_kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0, fiber_g: 0 };
  for (const item of items) {
    const grams = Number(item.quantity);
    if (!item.food_id || !item.food_snapshot || !Number.isFinite(grams) || grams <= 0 || grams > 5000) continue;
    resolved.push({ food_id: item.food_id, food_snapshot: item.food_snapshot, grams });
    const factor = grams / item.food_snapshot.basis_grams;
    totals.calories_kcal += item.food_snapshot.calories * factor;
    totals.protein_g += item.food_snapshot.protein_g * factor;
    totals.carbs_g += item.food_snapshot.carbs_g * factor;
    totals.fat_g += item.food_snapshot.fat_g * factor;
    totals.fiber_g += item.food_snapshot.fiber_g * factor;
  }
  const unresolved = items.length - resolved.length;
  function useDraft() {
    const parsed = mealSchema.safeParse({ title, slot, time, training_day: draft.training_day, items: resolved.map(({ food_id, grams }) => ({ food_id, grams })) });
    if (!parsed.success) { setError(parsed.error.issues.map((issue) => issue.message).join(' ')); return; }
    if (!reviewed || unresolved > 0) { setError('Review every item, then resolve or explicitly remove all unresolved items.'); return; }
    onUse({ title: parsed.data.title, slot: parsed.data.slot, time: parsed.data.time, items: resolved }, draft.date, draft.training_day);
  }
  return <section className="ai-parse-review" aria-labelledby={heading}><h3 id={heading}>Review every parsed item</h3><p>{draft.date} · {draft.training_day ? 'Training day' : 'Rest day'}. Nothing has been saved. Food matches and portions can be wrong; edit every item as needed. Counts such as “3 eggs” need your measured grams.</p>
    <fieldset className="reference-fields" disabled={disabled}><legend className="visually-hidden">Editable parsed draft</legend>
      <div className="nutrition-form-grid"><NutritionField label="Parsed meal title"><input value={title} maxLength={120} required onChange={(event) => { setTitle(event.target.value); setReviewed(false); }} /></NutritionField><NutritionField label="Parsed meal slot"><select value={slot} onChange={(event) => { setSlot(event.target.value as MealInput['slot']); setReviewed(false); }}>{Object.entries(mealSlotLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></NutritionField><NutritionField label="Parsed meal time"><input type="time" required value={time} onChange={(event) => { setTime(event.target.value); setReviewed(false); }} /></NutritionField></div>
      <ol className="ai-parse-items">{items.map((item, index) => <DraftFoodPicker key={item.key} item={item} index={index} onChange={(next) => { setItems((current) => current.map((value) => value.key === next.key ? next : value)); setReviewed(false); }} onRemove={() => { setItems((current) => current.filter((value) => value.key !== item.key)); setReviewed(false); }} />)}</ol>
      {items.length === 0 && <p>All items were removed. Start another parse or use manual meal logging.</p>}
      <div className="ai-partial-totals" role="status"><strong>{unresolved > 0 ? 'Partial totals — resolved items only' : 'Draft totals — not saved'}</strong><p>{resolved.length} of {items.length} items resolved · {unresolved} unresolved</p><p>{numberText(totals.calories_kcal)} kcal · P {numberText(totals.protein_g)} g · C {numberText(totals.carbs_g)} g · F {numberText(totals.fat_g)} g · Fiber {numberText(totals.fiber_g)} g</p></div>
      <p className="measurement-note">Draft values use catalog snapshots, never invented nutrients. The current food catalog is authoritative when you save. Changes here are not retained on reload; the original parsed draft is recoverable.</p>
      <label className="ai-review-confirmation"><input type="checkbox" checked={reviewed} disabled={unresolved > 0 || items.length === 0} onChange={(event) => setReviewed(event.target.checked)} /> I reviewed all food matches, measured portions, and removed items.</label>
      {error && <p className="error-notice" role="alert">{error}</p>}<button className="primary-button" type="button" disabled={!reviewed || unresolved > 0 || items.length === 0} onClick={useDraft}>Use edited draft</button>
    </fieldset>
    <p>Next: review the meal composer and explicitly choose Save meal. Parsing never logs a meal automatically.</p>
  </section>;
}
