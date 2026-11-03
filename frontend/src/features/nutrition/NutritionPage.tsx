import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { authSession } from '../../lib/api';
import { MealParsePanel } from '../ai/MealParsePanel';
import { useAuth } from '../auth/AuthProvider';
import { CatalogError } from '../library/ReferenceCatalog';
import { useProfile, utcToday } from '../profile/profile';
import { NutritionField, NutritionLoading } from './NutritionControls';
import { NutritionDayPanel } from './NutritionDayPanel';
import type { MealEditor } from './NutritionDayPanel';
import { NutritionHistory } from './NutritionHistory';
import { NutritionTrends } from './NutritionTrends';
import { useNutritionDay } from './nutrition';
import '../library/library.css';
import './nutrition.css';

function shiftDate(date: string, amount: number) {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + amount);
  return value.toISOString().slice(0, 10);
}
function AthleteNutrition({ initialWeeks }: { initialWeeks: number }) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const jobId = params.get('meal_parse_owner') === user?.id ? params.get('meal_parse') : null;
  useEffect(() => {
    if (params.has('meal_parse') && params.get('meal_parse_owner') !== user?.id) {
      setParams((current) => { const next = new URLSearchParams(current); next.delete('meal_parse'); next.delete('meal_parse_owner'); return next; }, { replace: true });
    }
    return authSession.subscribe(() => {
      if (authSession.getUser()?.id !== user?.id) setParams((current) => { const next = new URLSearchParams(current); next.delete('meal_parse'); next.delete('meal_parse_owner'); return next; }, { replace: true });
    });
  }, [params, setParams, user?.id]);
  function changeParseJob(id: string | null) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (id && user) { next.set('meal_parse', id); next.set('meal_parse_owner', user.id); }
      else { next.delete('meal_parse'); next.delete('meal_parse_owner'); }
      return next;
    }, { replace: true });
  }
  const [date, setDate] = useState(utcToday);
  const [editor, setEditor] = useState<MealEditor>(null);
  const query = useNutritionDay(date);
  const today = utcToday();
  function navigate(next: string) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(next) && next <= today && next >= '0001-01-01') setDate(next);
  }
  return <main id="main-content" className="nutrition-page"><header><span className="eyebrow"><span className="eyebrow-line" /> NUTRITION LOG</span><h1>Nutrition<span className="brand-accent">.</span></h1><p>Record real meals and water. Follow your saved targets and observed patterns.</p></header>
    <section className="connection-card nutrition-date-navigation" aria-label="Nutrition date navigation"><button type="button" className="secondary-button" disabled={editor !== null || date === '0001-01-01'} onClick={() => navigate(shiftDate(date, -1))}>Previous day</button><NutritionField label="Nutrition date (UTC calendar)"><input type="date" required min="0001-01-01" max={today} value={date} disabled={editor !== null} onChange={(event) => navigate(event.target.value)} /></NutritionField><button type="button" className="secondary-button" disabled={date >= today || editor !== null} onClick={() => navigate(shiftDate(date, 1))}>Next day</button><button type="button" className="text-button" disabled={date === today || editor !== null} onClick={() => navigate(today)}>Today</button>{editor !== null && <p className="measurement-note">Save or cancel the meal editor before changing dates.</p>}</section>
    {query.isPending && <NutritionLoading label={`Loading nutrition for ${date}…`} />}{query.isError && <CatalogError error={query.error} retry={() => void query.refetch()} />}
    {query.data && <><MealParsePanel date={date} trainingDay={query.data.training_day} jobId={jobId} editorOpen={editor !== null} onJobChange={changeParseJob} onUse={(draft, draftDate, trainingDay, parseJobId) => { setDate(draftDate); setEditor({ draft, parseJobId, trainingDay }); }} /><NutritionDayPanel key={date} day={query.data} editor={editor} setEditor={setEditor} onParsedSaved={() => changeParseJob(null)} /></>}
    <NutritionTrends initialWeeks={initialWeeks} endDate={date} /><NutritionHistory key={`history-${date}`} date={date} />
  </main>;
}
export function NutritionPage() {
  const { user } = useAuth();
  const profile = useProfile();
  if (profile.isPending) return <main id="main-content" className="nutrition-page"><NutritionLoading label="Loading athlete nutrition preferences…" /></main>;
  if (profile.isError) return <main id="main-content" className="nutrition-page"><CatalogError error={profile.error} retry={() => void profile.refetch()} /></main>;
  if (!user || !profile.data.profile) return null;
  return <AthleteNutrition key={user.id} initialWeeks={profile.data.profile.analysis_weeks} />;
}
