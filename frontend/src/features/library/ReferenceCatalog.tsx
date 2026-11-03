import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { classificationLabels, useExercises, useFoods, useMuscles } from './reference';
import type { Exercise, Food } from './reference';

const PAGE_SIZE = 12;
export function CatalogError({ error, retry }: { error: Error; retry: () => void }) {
  return <div className="error-notice" role="alert">{error.message}<div><button type="button" className="text-button" onClick={retry}>Try again</button></div></div>;
}

function Pagination({ offset, total, onChange, fetching }: { offset: number; total: number; onChange: (offset: number) => void; fetching: boolean }) {
  return <nav className="history-pagination" aria-label="Catalog pages">
    <button type="button" className="secondary-button" disabled={offset === 0 || fetching} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
    <span role="status">{total === 0 ? '0 results' : `${Math.min(offset + 1, total)}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}</span>
    <button type="button" className="secondary-button" disabled={offset + PAGE_SIZE >= total || fetching} onClick={() => onChange(offset + PAGE_SIZE)}>Next</button>
  </nav>;
}

export function OwnershipLabel({ custom }: { custom: boolean }) {
  return <span className={`catalog-badge${custom ? ' catalog-badge--custom' : ''}`}>{custom ? 'My custom' : 'Global · read-only'}</span>;
}

export function ExerciseDetails({ exercise }: { exercise: Exercise }) {
  const muscles = useMuscles();
  const names = new Map(muscles.data?.map((muscle) => [muscle.id, muscle.name]));
  return <>
    <p>{classificationLabels[exercise.classification]} · {exercise.equipment}</p>
    <dl className="catalog-metrics">
      <div><dt>MET</dt><dd>{exercise.met}</dd></div>
      <div><dt>Biomechanical multiplier</dt><dd>{exercise.biomechanical_multiplier}</dd></div>
      <div><dt>Measurement</dt><dd>{exercise.measurement_type === 'seconds' ? 'Seconds' : 'Repetitions'}</dd></div>
    </dl>
    <p className="catalog-muscles">Muscle contributions: {exercise.muscles.map((muscle) => `${names.get(muscle.muscle_id) ?? muscle.muscle_id} ${muscle.contribution}`).join(' · ')}</p>
  </>;
}
export function FoodDetails({ food }: { food: Food }) {
  return <>
    <p className="catalog-basis">Per {food.basis_grams} g · {food.calories} kcal</p>
    <dl className="catalog-metrics">
      <div><dt>Protein</dt><dd>{food.protein_g} g</dd></div>
      <div><dt>Carbohydrate</dt><dd>{food.carbs_g} g</dd></div>
      <div><dt>Fat</dt><dd>{food.fat_g} g</dd></div>
      <div><dt>Fiber</dt><dd>{food.fiber_g} g</dd></div>
    </dl>
  </>;
}

type CatalogProps<T> = { renderActions?: (item: T) => ReactNode };
export function ExerciseCatalog({ renderActions }: CatalogProps<Exercise>) {
  const id = useId();
  const { user } = useAuth();
  const [search, setSearch] = useState({ q: '', muscle: '', equipment: '' });
  const [filters, setFilters] = useState(search);
  const [offset, setOffset] = useState(0);
  const query = useExercises({ ...filters, offset, limit: PAGE_SIZE });
  const muscles = useMuscles();
  return <div className="catalog-browser">
    <form className="catalog-filters" onSubmit={(event) => { event.preventDefault(); setFilters(search); setOffset(0); }}>
      <div className="form-field"><label htmlFor={`${id}-search`}>Search exercises</label><input id={`${id}-search`} type="search" maxLength={120} value={search.q} onChange={(event) => setSearch({ ...search, q: event.target.value })} placeholder="Search by name" /></div>
      <div className="form-field"><label htmlFor={`${id}-muscle`}>Muscle</label><select id={`${id}-muscle`} value={search.muscle} onChange={(event) => setSearch({ ...search, muscle: event.target.value })} disabled={!muscles.data}><option value="">{muscles.isPending ? 'Loading muscles…' : 'All muscles'}</option>{muscles.data?.map((muscle) => <option key={muscle.id} value={muscle.id}>{muscle.name}</option>)}</select></div>
      <div className="form-field"><label htmlFor={`${id}-equipment`}>Equipment</label><input id={`${id}-equipment`} maxLength={80} value={search.equipment} onChange={(event) => setSearch({ ...search, equipment: event.target.value })} placeholder="e.g. bodyweight" /></div>
      <button type="submit" className="secondary-button">Apply filters</button>
      <button type="button" className="text-button" onClick={() => { const empty = { q: '', muscle: '', equipment: '' }; setSearch(empty); setFilters(empty); setOffset(0); }}>Clear</button>
    </form>
    {muscles.isError && <CatalogError error={muscles.error} retry={() => void muscles.refetch()} />}
    <div aria-busy={query.isFetching}>
      {query.isPending ? <p role="status" className="catalog-state">Loading exercises…</p> : query.isError ? <CatalogError error={query.error} retry={() => void query.refetch()} /> : <>
        {query.data.items.length === 0 ? <p className="catalog-state" role="status">No exercises on this page. Try clearing filters, returning to the previous page, or adding your own custom exercise.</p> : <ul className="catalog-grid">{query.data.items.filter((item) => item.owner_id === null || item.owner_id === user?.id).map((exercise) => <li key={exercise.id} className="catalog-card"><OwnershipLabel custom={exercise.is_custom} /><h3>{exercise.name}</h3><ExerciseDetails exercise={exercise} />{renderActions?.(exercise)}</li>)}</ul>}
        <Pagination offset={offset} total={query.data.total} onChange={setOffset} fetching={query.isFetching} />
      </>}
    </div>
  </div>;
}

export function FoodCatalog({ renderActions }: CatalogProps<Food>) {
  const id = useId();
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const [q, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const query = useFoods({ q, offset, limit: PAGE_SIZE });
  return <div className="catalog-browser">
    <p className="measurement-note">All food values are normalized to 100 g, not a serving. Fiber is included in total carbohydrate.</p>
    <form className="catalog-filters catalog-filters--food" onSubmit={(event) => { event.preventDefault(); setQuery(search); setOffset(0); }}>
      <div className="form-field"><label htmlFor={`${id}-search`}>Search foods</label><input id={`${id}-search`} type="search" maxLength={120} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name" /></div>
      <button type="submit" className="secondary-button">Search</button>
      <button type="button" className="text-button" onClick={() => { setSearch(''); setQuery(''); setOffset(0); }}>Clear</button>
    </form>
    <div aria-busy={query.isFetching}>
      {query.isPending ? <p role="status" className="catalog-state">Loading foods…</p> : query.isError ? <CatalogError error={query.error} retry={() => void query.refetch()} /> : <>
        {query.data.items.length === 0 ? <p className="catalog-state" role="status">No foods on this page. Try clearing search, returning to the previous page, or adding your own custom food.</p> : <ul className="catalog-grid">{query.data.items.filter((item) => item.owner_id === null || item.owner_id === user?.id).map((food) => <li key={food.id} className="catalog-card"><OwnershipLabel custom={food.is_custom} /><h3>{food.name}</h3><FoodDetails food={food} />{renderActions?.(food)}</li>)}</ul>}
        <Pagination offset={offset} total={query.data.total} onChange={setOffset} fetching={query.isFetching} />
      </>}
    </div>
  </div>;
}

export function ExerciseSearchPicker({ onSelect, disabled = false }: { onSelect: (exercise: Exercise) => void; disabled?: boolean }) {
  return <ExerciseCatalog renderActions={(exercise) => <button type="button" className="secondary-button" disabled={disabled} onClick={() => onSelect(exercise)}>Select <span className="visually-hidden">{exercise.name}</span></button>} />;
}
export function FoodSearchPicker({ onSelect, disabled = false }: { onSelect: (food: Food) => void; disabled?: boolean }) {
  return <FoodCatalog renderActions={(food) => <button type="button" className="secondary-button" disabled={disabled} onClick={() => onSelect(food)}>Select <span className="visually-hidden">{food.name}</span></button>} />;
}
