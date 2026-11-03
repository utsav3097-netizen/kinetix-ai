import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { Announcements } from './Announcements';
import { useAdminAnalytics, useAdminAnnouncements, useAdminAudit, useAdminExercises, useAdminFoods, useAdminMutation, useAdminSettings } from './admin';
import './admin.css';
const emptyExercise = { name: '', equipment: 'bodyweight', met: '5', biomechanical_multiplier: '0.7', classification: 'upper_compound', measurement_type: 'reps', muscles: '[]' };
const emptyFood = { name: '', calories: '0', protein_g: '0', carbs_g: '0', fat_g: '0', fiber_g: '0' };

export function AdminPage() {
  const { user } = useAuth();
  const analytics = useAdminAnalytics();
  const settings = useAdminSettings();
  const exercises = useAdminExercises();
  const foods = useAdminFoods();
  const announcements = useAdminAnnouncements();
  const audit = useAdminAudit();
  const mutate = useAdminMutation();
  const [exercise, setExercise] = useState(emptyExercise);
  const [food, setFood] = useState(emptyFood);
  const [settingKey, setSettingKey] = useState('coach_prompt');
  const [settingValue, setSettingValue] = useState('');
  const [announcement, setAnnouncement] = useState({ title: '', body: '', starts_at: '', ends_at: '' });
  if (user?.role !== 'admin') return <main className="page-shell"><section className="connection-card"><h1>Administrator access required</h1><p>This area is restricted to administrators.</p></section></main>;

  const saveExercise = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await mutate.mutateAsync({ path: '/admin/exercises', input: { ...exercise, met: Number(exercise.met), biomechanical_multiplier: Number(exercise.biomechanical_multiplier), muscles: JSON.parse(exercise.muscles) } });
      setExercise(emptyExercise);
    } catch { /* server validation is rendered by the API client in the shared shell */ }
  };
  const saveFood = async (event: FormEvent) => {
    event.preventDefault();
    await mutate.mutateAsync({ path: '/admin/foods', input: { ...food, calories: Number(food.calories), protein_g: Number(food.protein_g), carbs_g: Number(food.carbs_g), fat_g: Number(food.fat_g), fiber_g: Number(food.fiber_g) } });
    setFood(emptyFood);
  };
  const saveSetting = async (event: FormEvent) => {
    event.preventDefault();
    let value: unknown = settingValue;
    if (settingKey === 'progression_policy') value = JSON.parse(settingValue);
    await mutate.mutateAsync({ path: `/admin/settings/${settingKey}`, method: 'PUT', input: { value } });
    setSettingValue('');
  };
  const saveAnnouncement = async (event: FormEvent) => {
    event.preventDefault();
    await mutate.mutateAsync({ path: '/admin/announcements', input: { ...announcement, starts_at: new Date(announcement.starts_at).toISOString(), ends_at: announcement.ends_at ? new Date(announcement.ends_at).toISOString() : null } });
    setAnnouncement({ title: '', body: '', starts_at: '', ends_at: '' });
  };
  return <main className="page-shell" aria-labelledby="admin-heading">
    <h1 id="admin-heading">Administration and audit center</h1>
    <section className="connection-card"><h2>System health and analytics</h2>{analytics.isPending ? <p>Loading…</p> : analytics.data && <dl className="metric-grid"><div><dt>Users</dt><dd>{analytics.data.users.total}</dd></div><div><dt>Onboarding completion</dt><dd>{Math.round(analytics.data.onboarding.completion_rate * 100)}%</dd></div><div><dt>Workout logs</dt><dd>{analytics.data.logging.workout_sessions}</dd></div><div><dt>AI success rate</dt><dd>{Math.round((analytics.data.ai.success_rate ?? 0) * 100)}%</dd></div><div><dt>AI average latency</dt><dd>{analytics.data.ai.average_latency_ms ?? '—'} ms</dd></div><div><dt>Database</dt><dd>{analytics.data.health.database}</dd></div></dl>}</section>
    <section className="connection-card"><h2>Global exercise</h2><form onSubmit={saveExercise} className="form-grid"><input aria-label="Exercise name" placeholder="Name" required value={exercise.name} onChange={e => setExercise({ ...exercise, name: e.target.value })} /><input aria-label="Equipment" placeholder="Equipment" required value={exercise.equipment} onChange={e => setExercise({ ...exercise, equipment: e.target.value })} /><input aria-label="MET" type="number" step="0.1" value={exercise.met} onChange={e => setExercise({ ...exercise, met: e.target.value })} /><input aria-label="Biomechanical multiplier" type="number" step="0.01" value={exercise.biomechanical_multiplier} onChange={e => setExercise({ ...exercise, biomechanical_multiplier: e.target.value })} /><select aria-label="Classification" value={exercise.classification} onChange={e => setExercise({ ...exercise, classification: e.target.value })}><option value="upper_compound">Upper compound</option><option value="lower_compound">Lower compound</option><option value="isolation">Isolation</option></select><select aria-label="Measurement" value={exercise.measurement_type} onChange={e => setExercise({ ...exercise, measurement_type: e.target.value })}><option value="reps">Reps</option><option value="seconds">Seconds</option></select><input aria-label="Muscle mappings JSON" value={exercise.muscles} onChange={e => setExercise({ ...exercise, muscles: e.target.value })} /><button type="submit">Create exercise</button></form><ul>{exercises.data?.items.map(item => <li key={item.id}>{item.name} <button type="button" onClick={() => mutate.mutate({ path: `/admin/exercises/${item.id}`, method: 'DELETE' })}>Soft delete</button></li>)}</ul></section>
    <section className="connection-card"><h2>Global food</h2><form onSubmit={saveFood} className="form-grid">{Object.keys(emptyFood).map(key => <input key={key} aria-label={key} placeholder={key} required value={food[key as keyof typeof food]} onChange={e => setFood({ ...food, [key]: e.target.value })} />)}<button type="submit">Create food</button></form><ul>{foods.data?.items.map(item => <li key={item.id}>{item.name} <button type="button" onClick={() => mutate.mutate({ path: `/admin/foods/${item.id}`, method: 'DELETE' })}>Soft delete</button></li>)}</ul></section>
    <section className="connection-card"><h2>Validated policy setting</h2><form onSubmit={saveSetting} className="form-grid"><select aria-label="Setting key" value={settingKey} onChange={e => setSettingKey(e.target.value)}><option value="coach_prompt">Coach prompt</option><option value="meal_prompt">Meal prompt</option><option value="progression_policy">Progression policy</option></select><textarea aria-label="Setting value" required value={settingValue} onChange={e => setSettingValue(e.target.value)} placeholder={settingKey === 'progression_policy' ? '{"upper_increment_kg":2.5,"lower_increment_kg":5,"deload_multiplier":0.9}' : 'Prompt text'} /><button type="submit">Save setting</button></form><ul>{settings.data?.map(item => <li key={item.key}><strong>{item.key}</strong>: {JSON.stringify(item.value)}</li>)}</ul></section>
    <section className="connection-card"><h2>Scheduled announcement</h2><form onSubmit={saveAnnouncement} className="form-grid"><input aria-label="Announcement title" required placeholder="Title" value={announcement.title} onChange={e => setAnnouncement({ ...announcement, title: e.target.value })} /><textarea aria-label="Announcement body" required placeholder="Message" value={announcement.body} onChange={e => setAnnouncement({ ...announcement, body: e.target.value })} /><label>Starts <input type="datetime-local" required value={announcement.starts_at} onChange={e => setAnnouncement({ ...announcement, starts_at: e.target.value })} /></label><label>Ends (optional) <input type="datetime-local" value={announcement.ends_at} onChange={e => setAnnouncement({ ...announcement, ends_at: e.target.value })} /></label><button type="submit">Schedule announcement</button></form><ul>{announcements.data?.items.map(item => <li key={item.id}>{item.title} — {item.starts_at} <button type="button" onClick={() => mutate.mutate({ path: `/admin/announcements/${item.id}`, method: 'DELETE' })}>Delete</button></li>)}</ul></section>
    <Announcements />
    <section className="connection-card"><h2>Audit history</h2><ul>{audit.data?.items.map(item => <li key={item.id}>{item.created_at} — {item.action} {item.resource_type} {item.resource_id}</li>)}</ul></section>
  </main>;
}
