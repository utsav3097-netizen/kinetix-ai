import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { CatalogError } from '../library/ReferenceCatalog';
import { failureMessage, scoreText } from '../nutrition/nutrition';
import { useProfile, utcToday } from '../profile/profile';
import { Field, LoadingWorkout } from '../workouts/WorkoutForms';
import { numberText } from '../workouts/workouts';
import { PlanningPagination, ReportCharts } from './PlanningCharts';
import { usePlanningMutation, useReport, useReports } from './plans';
import type { ReportView } from './plans';
import '../workouts/workouts.css';
import './planning.css';

export function ReportsPage() {
  const { user } = useAuth();
  return <ReportsContent key={user?.id} />;
}
function ReportsContent() {
  const [params, setParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const profile = useProfile();
  const [weeks, setWeeks] = useState(profile.data?.profile?.analysis_weeks ?? 1);
  const [endDate, setEndDate] = useState(utcToday());
  const list = useReports(offset);
  const selected = useReport(params.get('id') ?? '');
  const generate = usePlanningMutation<ReportView>();
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await generate.mutateAsync({ path: '/reports', input: { weeks, end_date: endDate } });
      setOffset(0);
      setParams({ id: result.id });
    } catch { /* The API error remains visible in the form. */ }
  }
  const report = selected.data;
  return <main id="main-content" className="planning-page"><header className="dashboard-intro"><span className="eyebrow">FROZEN RECORDS · OBSERVED SIGNALS</span><h1>Your <span>reports.</span></h1><p>Completed weekly and selected analysis-period reports are materialized when you open reports or the dashboard after a boundary, not by a background scheduler. Every saved report stays unchanged when source records are corrected.</p><Link className="home-link" to="/plans">Explore training paths and plans</Link></header>
    <section className="connection-card"><h2>Create a report snapshot</h2><form onSubmit={(event) => void submit(event)}><fieldset className="reference-fields" disabled={generate.isPending}><legend className="visually-hidden">Report date range</legend><div className="planning-form-grid"><Field label="Analysis window"><select value={weeks} onChange={(event) => setWeeks(Number(event.target.value) as typeof weeks)}>{[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value} {value === 1 ? 'week' : 'weeks'}</option>)}</select></Field><Field label="Window ending (UTC date)"><input type="date" required max={utcToday()} value={endDate} onChange={(event) => setEndDate(event.target.value)} /></Field></div><p>Creates a new immutable rolling-window snapshot, even if a prior report covers the same dates. Partial history is shown explicitly.</p><button type="submit" className="primary-button">{generate.isPending ? 'Generating report…' : 'Generate report'}</button></fieldset>{generate.error && <div className="error-notice" role="alert">{failureMessage(generate.error)}</div>}</form></section>
    <section className="connection-card"><h2>Report history</h2>{list.isPending ? <LoadingWorkout label="Loading reports…" /> : list.isError ? <CatalogError error={list.error} retry={() => void list.refetch()} /> : <>{list.data.items.length === 0 ? <p>No saved reports yet. Generate a snapshot to review your available records.</p> : <ul className="planning-record-list">{list.data.items.map((item) => <li key={item.id}><div><strong>{item.kind} · {item.window_start} – {item.window_end}</strong><p>{item.logged_training_days}/{item.expected_days} training days · {item.logged_nutrition_days}/{item.expected_days} nutrition days · Macro score {scoreText(item.macro_adherence_score)}</p><span className="detail-note">Revision {item.revision} · Saved {new Date(item.created_at).toLocaleString()}</span></div><button type="button" className="secondary-button" aria-pressed={params.get('id') === item.id} onClick={() => setParams({ id: item.id })}>View report</button></li>)}</ul>}<PlanningPagination offset={offset} total={list.data.total} onChange={setOffset} label="Reports" /></>}</section>
    {params.get('id') && <section aria-label="Selected report">{selected.isPending ? <LoadingWorkout label="Loading saved report…" /> : selected.isError ? <CatalogError error={selected.error} retry={() => void selected.refetch()} /> : report && <><div className="connection-card"><h2>{report.window_start} – {report.window_end}</h2><p>{report.data.explanation}</p><p><strong>{report.data.history_sufficient ? 'History-backed observations' : 'Limited history / conservative assessment'}</strong></p><dl className="catalog-metrics"><div><dt>Sessions</dt><dd>{report.data.total_sessions}</dd></div><div><dt>Volume</dt><dd>{numberText(report.data.total_volume_kg)} kg·reps</dd></div><div><dt>Training coverage</dt><dd>{report.logged_training_days}/{report.expected_days} days</dd></div><div><dt>Nutrition coverage</dt><dd>{report.logged_nutrition_days}/{report.expected_days} days</dd></div></dl><p className="detail-note">Source snapshot: {report.data.source_record_ids.length} source records. Training gaps are not evidence of no exercise.</p><Link className="primary-button" to={`/plans?report=${encodeURIComponent(report.id)}`}>Choose a path using this report</Link></div><ReportCharts report={report} unit={profile.data?.profile?.display_unit ?? 'kg'} /></>}</section>}
  </main>;
}
