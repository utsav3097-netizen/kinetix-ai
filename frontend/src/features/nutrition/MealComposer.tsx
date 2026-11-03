import { useEffect, useId, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { CatalogError } from '../library/ReferenceCatalog';
import { FoodForm } from '../library/ReferenceForms';
import type { Food } from '../library/reference';
import { NutritionField, NutritionLoading, NutritionPagination } from './NutritionControls';
import { assertNutritionAccount, dayPath, failureMessage, mealPath, mealSchema, mealSlotLabels, numberText, useNutritionFoods, useNutritionMutation } from './nutrition';
import type { MealDraft, MealInput, MealView } from './nutrition';

export type MealComposerProps = { date: string; trainingDay: boolean; meal?: MealView; initialDraft?: MealDraft; onSaved: () => void; onCancel: () => void };
type EditableItem = MealDraft['items'][number] & { key: string; quantity: string };

export function CustomFoodForm({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const { user } = useAuth();
  const [error, setError] = useState<string | null>(null);
  return <div onSubmitCapture={(event) => {
    try { assertNutritionAccount(user?.id); }
    catch (failure) { event.preventDefault(); event.stopPropagation(); setError(failureMessage(failure)); }
  }}>{error && <p className="error-notice" role="alert">{error}</p>}<FoodForm onSaved={() => { try { assertNutritionAccount(user?.id); onSaved(); } catch (failure) { setError(failureMessage(failure)); } }} onCancel={onCancel} /></div>;
}

/** Receives explicit food-backed draft items; saving is always a separate user action. */
export function MealComposer({ date, trainingDay, meal, initialDraft, onSaved, onCancel }: MealComposerProps) {
  const prefix = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const sequence = useRef(0);
  useEffect(() => { heading.current?.focus(); }, []);
  const initial = meal ? { title: meal.title, slot: meal.slot, time: meal.time, items: meal.items.map((item) => ({ food_id: item.food_id, item_id: item.id, grams: item.grams, food_snapshot: item.food_snapshot })) } : initialDraft;
  const [title, setTitle] = useState(initial?.title ?? '');
  const [slot, setSlot] = useState<MealInput['slot']>(initial?.slot ?? 'breakfast');
  const [time, setTime] = useState(initial?.time ?? '');
  const [items, setItems] = useState<EditableItem[]>(() => (initial?.items ?? []).map((item, index) => ({ ...item, key: `initial-${index}`, quantity: String(item.grams) })));
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [customFood, setCustomFood] = useState(false);
  const [confirmation, setConfirmation] = useState<MealInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const foods = useNutritionFoods(search, offset);
  const save = useNutritionMutation();
  const frozen = save.isPending || confirmation !== null;
  function addFood(food: Food) {
    setItems((current) => [...current, { key: `added-${sequence.current++}`, food_id: food.id, grams: 100, quantity: '100', food_snapshot: { name: food.name, basis_grams: food.basis_grams, calories: food.calories, protein_g: food.protein_g, carbs_g: food.carbs_g, fat_g: food.fat_g, fiber_g: food.fiber_g } }]);
    setError(null);
  }
  async function persist(input: MealInput) {
    setError(null);
    try { await save.mutateAsync({ path: meal ? mealPath(meal.id) : `${dayPath(date)}/meals`, method: meal ? 'PUT' : 'POST', input }); onSaved(); }
    catch (failure) { setError(failureMessage(failure)); setConfirmation(null); }
  }
  function submit() {
    const parsed = mealSchema.safeParse({ title, slot, time, training_day: trainingDay, items: items.map((item) => ({ food_id: item.food_id, grams: Number(item.quantity), ...(item.item_id ? { item_id: item.item_id } : {}) })) });
    if (!parsed.success) { setError(parsed.error.issues.map((issue) => issue.message).join(' ')); return; }
    setError(null);
    if (meal) setConfirmation(parsed.data);
    else void persist(parsed.data);
  }
  return <section className="connection-card nutrition-composer" aria-labelledby={`${prefix}-heading`}>
    <h2 id={`${prefix}-heading`} ref={heading} tabIndex={-1}>{meal ? 'Edit meal' : 'Compose meal'}</h2><p>{date} · {trainingDay ? 'Training day' : 'Rest day'}. Food labels below are per 100 g; enter the grams actually consumed.</p>
    {initialDraft && <p className="measurement-note">Reviewed AI draft — not yet saved. Check food matches, grams, title, and time below, then explicitly Save meal. Current library values are used at final save; these draft labels may have changed since parsing.</p>}
    {meal && <p className="measurement-note">Existing items keep their saved nutrient snapshots when you change grams, even if the library changed. To replace an item with current library values, remove it and add the food again. Saving records a correction without rewriting source history.</p>}
    <fieldset className="reference-fields" disabled={frozen}>
      <legend className="visually-hidden">Food selection</legend>
      <form className="nutrition-search" onSubmit={(event) => { event.preventDefault(); setSearch(searchInput.trim()); setOffset(0); }}><NutritionField label="Search food library"><input type="search" value={searchInput} maxLength={120} onChange={(event) => setSearchInput(event.target.value)} /></NutritionField><button className="secondary-button" type="submit">Search foods</button><button className="text-button" type="button" onClick={() => { setSearchInput(''); setSearch(''); setOffset(0); }}>Clear search</button></form>
      {foods.isPending ? <NutritionLoading label="Loading foods…" /> : foods.isError ? <CatalogError error={foods.error} retry={() => void foods.refetch()} /> : <><ul className="nutrition-food-results">{foods.data.items.map((food) => <li key={food.id}><div><strong>{food.name}</strong><p>Per 100 g: {numberText(food.calories)} kcal · P {numberText(food.protein_g)} g · C {numberText(food.carbs_g)} g · F {numberText(food.fat_g)} g · Fiber {numberText(food.fiber_g)} g</p></div><button className="secondary-button" type="button" disabled={items.length >= 50} onClick={() => addFood(food)}>Add<span className="visually-hidden"> {food.name}</span></button></li>)}</ul>{foods.data.total === 0 && <p>No foods match. Search another name or create your own food from its label.</p>}<NutritionPagination label="Food search pages" offset={offset} total={foods.data.total} limit={10} onChange={setOffset} /></>}
      <button type="button" className="secondary-button" disabled={customFood} onClick={() => setCustomFood(true)}>Create custom food</button>
      {customFood && <CustomFoodForm onSaved={() => { setCustomFood(false); setSearch(''); setSearchInput(''); setOffset(0); }} onCancel={() => setCustomFood(false)} />}
    </fieldset>
    <form className="reference-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <fieldset disabled={frozen} className="reference-fields"><legend className="visually-hidden">Meal details</legend><div className="nutrition-form-grid"><NutritionField label="Meal title"><input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={120} /></NutritionField><NutritionField label="Meal slot"><select value={slot} onChange={(event) => setSlot(event.target.value as MealInput['slot'])}>{Object.entries(mealSlotLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></NutritionField><NutritionField label="Meal time"><input type="time" value={time} onChange={(event) => setTime(event.target.value)} required /></NutritionField></div>
        <h3>Meal items ({items.length}/50)</h3>{items.length === 0 && <p>Add a food above to begin your meal.</p>}<ul className="nutrition-draft-items">{items.map((item, index) => <li key={item.key}><div><strong>{item.food_snapshot.name}</strong><p>{item.item_id ? 'Saved snapshot' : 'Library label'} per 100 g: {numberText(item.food_snapshot.calories)} kcal · P {numberText(item.food_snapshot.protein_g)} g · C {numberText(item.food_snapshot.carbs_g)} g · F {numberText(item.food_snapshot.fat_g)} g</p></div><NutritionField label={`Consumed grams — item ${index + 1}`}><input type="number" inputMode="decimal" min="0" max="5000" step="any" required value={item.quantity} onChange={(event) => setItems((current) => current.map((entry) => entry.key === item.key ? { ...entry, quantity: event.target.value } : entry))} /></NutritionField><button className="text-button danger-text" type="button" onClick={() => setItems((current) => current.filter((entry) => entry.key !== item.key))}>Remove<span className="visually-hidden"> {item.food_snapshot.name} from draft</span></button></li>)}</ul>
      </fieldset>
      {error && <p className="error-notice" role="alert">{error}</p>}
      {confirmation ? <div className="nutrition-confirm" role="group" aria-labelledby={`${prefix}-confirm`}><p id={`${prefix}-confirm`}>Save this correction to “{title}”? Current totals will change; original entries stay in history.</p><div className="session-actions"><button className="primary-button" type="button" disabled={save.isPending} onClick={() => void persist(confirmation)}>{save.isPending ? 'Saving…' : 'Confirm meal changes'}</button><button className="secondary-button" type="button" disabled={save.isPending} onClick={() => setConfirmation(null)}>Keep editing</button></div></div> : <div className="session-actions"><button className="primary-button" type="submit" disabled={save.isPending || items.length === 0}>{save.isPending ? 'Saving…' : meal ? 'Review meal changes' : 'Save meal'}</button><button className="secondary-button" type="button" disabled={save.isPending} onClick={onCancel}>Cancel</button></div>}
    </form>
  </section>;
}
