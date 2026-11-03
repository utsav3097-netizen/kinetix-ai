import { useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { ExerciseCatalog, FoodCatalog } from './ReferenceCatalog';
import { ExerciseForm, FoodForm } from './ReferenceForms';
import { useExerciseMutation, useFoodMutation } from './reference';
import type { Exercise, Food } from './reference';
import './library.css';

function ExerciseLibrary() {
  const { user } = useAuth();
  const [editor, setEditor] = useState<Exercise | 'new' | null>(null);
  const [notice, setNotice] = useState('');
  const remove = useExerciseMutation();
  const createButton = useRef<HTMLButtonElement>(null);
  const editTrigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setEditor(null); requestAnimationFrame(() => (editTrigger.current?.isConnected ? editTrigger.current : createButton.current)?.focus()); };
  async function deleteExercise(exercise: Exercise) {
    if (exercise.owner_id !== user?.id || !exercise.is_custom) return;
    if (!window.confirm(`Delete your custom exercise “${exercise.name}”? This cannot be undone.`)) return;
    setNotice('');
    try {
      await remove.mutateAsync({ action: 'delete', id: exercise.id });
      setNotice(`Deleted ${exercise.name}.`);
      createButton.current?.focus();
    } catch { /* Mutation error is shown below with its server message. */ }
  }
  return <section aria-labelledby="exercise-library-heading">
    <div className="library-section-heading"><h2 id="exercise-library-heading">Exercise catalog</h2><button ref={createButton} type="button" className="primary-button" disabled={editor !== null || remove.isPending} onClick={() => { editTrigger.current = null; setNotice(''); remove.reset(); setEditor('new'); }}>Create custom exercise</button></div>
    {notice && <p className="success-notice" role="status">{notice}</p>}
    {remove.isError && <div className="error-notice" role="alert">{remove.error.message}</div>}
    {editor !== null && <ExerciseForm key={editor === 'new' ? 'new' : editor.id} exercise={editor === 'new' ? undefined : editor} onCancel={close} onSaved={() => { setNotice('Custom exercise saved.'); close(); }} />}
    <div hidden={editor !== null}>
      <ExerciseCatalog renderActions={(exercise) => exercise.is_custom && exercise.owner_id === user?.id ? <div className="session-actions">
        <button type="button" className="secondary-button" disabled={remove.isPending} onClick={(event) => { editTrigger.current = event.currentTarget; setNotice(''); remove.reset(); setEditor(exercise); }}>Edit<span className="visually-hidden"> {exercise.name}</span></button>
        <button type="button" className="text-button danger-text" disabled={remove.isPending} onClick={() => void deleteExercise(exercise)}>{remove.isPending && remove.variables?.id === exercise.id ? 'Deleting…' : 'Delete'}<span className="visually-hidden"> {exercise.name}</span></button>
      </div> : null} />
    </div>
  </section>;
}

function FoodLibrary() {
  const { user } = useAuth();
  const [editor, setEditor] = useState<Food | 'new' | null>(null);
  const [notice, setNotice] = useState('');
  const remove = useFoodMutation();
  const createButton = useRef<HTMLButtonElement>(null);
  const editTrigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setEditor(null); requestAnimationFrame(() => (editTrigger.current?.isConnected ? editTrigger.current : createButton.current)?.focus()); };
  async function deleteFood(food: Food) {
    if (food.owner_id !== user?.id || !food.is_custom) return;
    if (!window.confirm(`Delete your custom food “${food.name}”? This cannot be undone.`)) return;
    setNotice('');
    try {
      await remove.mutateAsync({ action: 'delete', id: food.id });
      setNotice(`Deleted ${food.name}.`);
      createButton.current?.focus();
    } catch { /* Mutation error is shown below with its server message. */ }
  }
  return <section aria-labelledby="food-library-heading">
    <div className="library-section-heading"><h2 id="food-library-heading">Food catalog</h2><button ref={createButton} type="button" className="primary-button" disabled={editor !== null || remove.isPending} onClick={() => { editTrigger.current = null; setNotice(''); remove.reset(); setEditor('new'); }}>Create custom food</button></div>
    {notice && <p className="success-notice" role="status">{notice}</p>}
    {remove.isError && <div className="error-notice" role="alert">{remove.error.message}</div>}
    {editor !== null && <FoodForm key={editor === 'new' ? 'new' : editor.id} food={editor === 'new' ? undefined : editor} onCancel={close} onSaved={() => { setNotice('Custom food saved.'); close(); }} />}
    <div hidden={editor !== null}>
      <FoodCatalog renderActions={(food) => food.is_custom && food.owner_id === user?.id ? <div className="session-actions">
        <button type="button" className="secondary-button" disabled={remove.isPending} onClick={(event) => { editTrigger.current = event.currentTarget; setNotice(''); remove.reset(); setEditor(food); }}>Edit<span className="visually-hidden"> {food.name}</span></button>
        <button type="button" className="text-button danger-text" disabled={remove.isPending} onClick={() => void deleteFood(food)}>{remove.isPending && remove.variables?.id === food.id ? 'Deleting…' : 'Delete'}<span className="visually-hidden"> {food.name}</span></button>
      </div> : null} />
    </div>
  </section>;
}

export function LibraryPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const catalog = params.get('catalog') === 'foods' ? 'foods' : 'exercises';
  return <main id="main-content" className="library-page">
    <header className="dashboard-intro">
      <span className="eyebrow"><span className="eyebrow-line" /> YOUR REFERENCE LIBRARY</span>
      <h1>Know your <span>building blocks.</span></h1>
      <p className="intro-copy">Browse global exercises and foods, or maintain private custom entries for your training and nutrition.</p>
      <Link to="/" className="home-link">Back to dashboard</Link>
    </header>
    <div className="library-switch" role="group" aria-label="Choose catalog">
      <button className={catalog === 'exercises' ? 'primary-button' : 'secondary-button'} type="button" aria-pressed={catalog === 'exercises'} onClick={() => setParams({ catalog: 'exercises' })}>Exercises</button>
      <button className={catalog === 'foods' ? 'primary-button' : 'secondary-button'} type="button" aria-pressed={catalog === 'foods'} onClick={() => setParams({ catalog: 'foods' })}>Foods</button>
    </div>
    {catalog === 'exercises' ? <ExerciseLibrary key={user?.id} /> : <FoodLibrary key={user?.id} />}
  </main>;
}
