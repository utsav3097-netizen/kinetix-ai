import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { CatalogError } from '../library/ReferenceCatalog';
import { failureMessage } from '../nutrition/nutrition';
import { useProfile, utcToday } from '../profile/profile';
import { Field, LoadingWorkout } from '../workouts/WorkoutForms';
import type { Unit } from '../workouts/workouts';
import { PlanChart } from './PlanChart';
import { PlanEditor } from './PlanEditor';
import { PlanningPagination } from './PlanningCharts';
import { upcomingMonday, useActivePlan, useDraft, useDrafts, usePaths, usePlanningMutation, useVersion, useVersions } from './plans';
import type { DraftView, PlanPath, VersionView } from './plans';
import '../workouts/workouts.css';
import './planning.css';

export function PlansPage() {
  const { user } = useAuth();
  return <PlansContent key={user?.id} />;
}
function PlansContent() {
  const [params, setParams] = useSearchParams();
  const profile = useProfile();
  const paths = usePaths();
  const active = useActivePlan();
  const [path, setPath] = useState<PlanPath>('cutting');
  const [startsOn, setStartsOn] = useState(upcomingMonday);
  const [draftOffset, setDraftOffset] = useState(0);
  const [versionOffset, setVersionOffset] = useState(0);
  const drafts = useDrafts(draftOffset);
  const versions = useVersions(versionOffset);
  const generate = usePlanningMutation<DraftView>();
  const reportId = params.get('report');
  const draftId = params.get('draft');
  const versionId = params.get('version');
  function selectDraft(draft: DraftView) { setDraftOffset(0); setParams({ draft: draft.id }); }
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const draft = await generate.mutateAsync({ path: '/plans/drafts', input: { path, starts_on: startsOn, report_id: reportId ?? paths.data?.report_id ?? null } });
      selectDraft(draft);
    } catch { /* The generation error stays visible. */ }
  }
  const unit = profile.data?.profile?.display_unit ?? 'kg';
  return <main id="main-content" className="planning-page"><header className="dashboard-intro"><span className="eyebrow">DETERMINISTIC TARGETS · YOUR ACCEPTANCE</span><h1>Your next <span>seven days.</span></h1><p>Choose a path, review exact training and nutrition, then explicitly accept a version. Drafts do not change your active plan. Previous versions remain readable forever.</p><Link className="home-link" to="/reports">Review your frozen reports</Link></header>
    <section className="connection-card"><h2>Active accepted plan</h2>{active.isPending ? <LoadingWorkout label="Loading active plan…" /> : active.isError ? <CatalogError error={active.error} retry={() => void active.refetch()} /> : active.data ? <><p><strong>Version {active.data.version}: {active.data.title}</strong> · {active.data.starts_on} – {active.data.ends_on}</p><p>New nutrition days within these dates inherit this accepted plan's targets. Existing logged days keep their saved targets.</p><Link className="primary-button" to={`?version=${encodeURIComponent(active.data.id)}`}>View active version</Link></> : <p>No accepted plan yet. Generate and review a draft below; acceptance is a separate action.</p>}</section>
    <section aria-labelledby="path-heading"><h2 id="path-heading">Six training paths</h2>{paths.isPending ? <LoadingWorkout label="Loading evidence-based path options…" /> : paths.isError ? <CatalogError error={paths.error} retry={() => void paths.refetch()} /> : <div className="planning-paths">{paths.data.items.map((option) => <article className={`connection-card planning-path${path === option.id ? ' planning-path--selected' : ''}`} key={option.id}><h3>{option.title}</h3><p>{option.description}</p><p><strong>{option.assessment_required ? 'Conservative assessment required' : 'History-backed assessment available'}</strong></p><p>{option.evidence}</p><p className="detail-note">Nutrition phase: {option.phase.replaceAll('_', ' ')}</p><button type="button" className="secondary-button" aria-pressed={path === option.id} onClick={() => setPath(option.id)}>{path === option.id ? 'Selected' : 'Select path'}<span className="visually-hidden">: {option.title}</span></button></article>)}</div>}</section>
    <section className="connection-card"><h2>Generate a seven-day draft</h2><form onSubmit={(event) => void submit(event)}><fieldset className="reference-fields" disabled={generate.isPending || !paths.data}><legend className="visually-hidden">Draft generation</legend><div className="planning-form-grid"><Field label="Training path"><select value={path} onChange={(event) => setPath(event.target.value as PlanPath)}>{paths.data?.items.map((option) => <option key={option.id} value={option.id}>{option.title}</option>)}</select></Field><Field label="Starts on (UTC date)"><input type="date" required min={utcToday()} value={startsOn} onChange={(event) => setStartsOn(event.target.value)} /></Field></div>{reportId && <p>Using your selected report. <Link to={`/reports?id=${encodeURIComponent(reportId)}`}>Read source report</Link> · <button className="text-button" type="button" onClick={() => setParams({})}>Use latest report instead</button></p>}<p>Insufficient comparable history produces a clearly labeled conservative assessment, not invented progress. Meals use available real food records and backend-computed gram portions.</p><button type="submit" className="primary-button">{generate.isPending ? 'Generating draft…' : 'Generate draft plan'}</button></fieldset>{generate.error && <div className="error-notice" role="alert">{failureMessage(generate.error)}</div>}</form></section>
    {(draftId || versionId) && <PlanDetail key={`${draftId ?? ''}-${versionId ?? ''}`} draftId={draftId} versionId={versionId} activeId={active.data?.id} unit={unit} onDraft={selectDraft} onVersion={(version) => { setVersionOffset(0); setParams({ version: version.id }); }} />}
    <section className="connection-card"><h2>Draft history</h2>{drafts.isPending ? <LoadingWorkout label="Loading draft history…" /> : drafts.isError ? <CatalogError error={drafts.error} retry={() => void drafts.refetch()} /> : <>{drafts.data.items.length === 0 ? <p>No drafts yet.</p> : <ul className="planning-record-list">{drafts.data.items.map((draft) => <li key={draft.id}><div><strong>{draft.title}</strong><p>{draft.starts_on} – {draft.ends_on} · {draft.assessment_required ? 'Conservative assessment' : 'History-backed'}</p><span className="detail-note">Created {new Date(draft.created_at).toLocaleString()}{draft.based_on_draft_id ? ' · Edited from an earlier draft' : ''}{draft.parent_version_id ? ' · Based on an accepted version' : ''}</span></div><button type="button" className="secondary-button" onClick={() => setParams({ draft: draft.id })}>Review draft</button></li>)}</ul>}<PlanningPagination offset={draftOffset} total={drafts.data.total} onChange={setDraftOffset} label="Drafts" /></>}</section>
    <section className="connection-card"><h2>Accepted version history</h2>{versions.isPending ? <LoadingWorkout label="Loading accepted versions…" /> : versions.isError ? <CatalogError error={versions.error} retry={() => void versions.refetch()} /> : <>{versions.data.items.length === 0 ? <p>No accepted versions yet.</p> : <ul className="planning-record-list">{versions.data.items.map((version) => <li key={version.id}><div><strong>Version {version.version}: {version.title}{version.id === active.data?.id ? ' · Active' : ''}</strong><p>{version.starts_on} – {version.ends_on}</p><span className="detail-note">Accepted {new Date(version.accepted_at).toLocaleString()} · Immutable</span></div><button type="button" className="secondary-button" onClick={() => setParams({ version: version.id })}>View exact version</button></li>)}</ul>}<PlanningPagination offset={versionOffset} total={versions.data.total} onChange={setVersionOffset} label="Accepted versions" /></>}</section>
  </main>;
}
function PlanDetail({ draftId, versionId, activeId, unit, onDraft, onVersion }: { draftId: string | null; versionId: string | null; activeId: string | undefined; unit: Unit; onDraft: (draft: DraftView) => void; onVersion: (version: VersionView) => void }) {
  const draft = useDraft(draftId ?? '');
  const version = useVersion(versionId ?? '');
  const accept = usePlanningMutation<VersionView>();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const acceptTrigger = useRef<HTMLButtonElement>(null);
  const query = versionId ? version : draft;
  const detail = query.data;
  if (query.isPending) return <LoadingWorkout label="Loading exact saved plan…" />;
  if (query.isError) return <CatalogError error={query.error} retry={() => void query.refetch()} />;
  if (!detail) return null;
  const sourceDraftId = version.data?.draft_id ?? draftId;
  async function acceptDraft() {
    if (!draftId) return;
    try {
      const result = await accept.mutateAsync({ path: `/plans/drafts/${encodeURIComponent(draftId)}/accept`, input: {} });
      onVersion(result);
    } catch { /* Acceptance failure is shown with the confirmation. */ }
  }
  return <section className="planning-detail" aria-label="Exact saved plan"><div className="connection-card"><span className="eyebrow">{version.data ? `IMMUTABLE VERSION ${version.data.version}${activeId === version.data.id ? ' · ACTIVE' : ''}` : 'DRAFT · NOT AN ACCEPTANCE'}</span><h2>{detail.title}</h2><p>{detail.starts_on} – {detail.ends_on}</p>{version.data && <p>Accepted {new Date(version.data.accepted_at).toLocaleString()}. This version cannot be overwritten.</p>}<div className="session-actions"><button type="button" className="secondary-button" disabled={accept.isPending || editing} onClick={() => { setEditing(true); setConfirming(false); }}>Edit into new draft</button>{!versionId && <button ref={acceptTrigger} type="button" className="primary-button" disabled={accept.isPending || editing} aria-expanded={confirming} aria-controls="accept-plan-confirmation" onClick={() => setConfirming(true)}>Accept this draft</button>}</div>{confirming && <div id="accept-plan-confirmation" className="revoke-confirmation" role="group" aria-labelledby="accept-plan-heading"><h3 id="accept-plan-heading">Accept this exact plan?</h3><p>This creates an immutable accepted version, makes it active, and changes your profile phase to {detail.data.profile_snapshot.phase.replaceAll('_', ' ')}. New nutrition days inside its dates use these targets; existing days stay unchanged. No workout or food entries are created.</p><div className="session-actions"><button type="button" className="primary-button" autoFocus disabled={accept.isPending} onClick={() => void acceptDraft()}>{accept.isPending ? 'Accepting…' : 'Confirm acceptance'}</button><button type="button" className="secondary-button" disabled={accept.isPending} onClick={() => { setConfirming(false); acceptTrigger.current?.focus(); }}>Cancel</button></div></div>}{accept.error && <div className="error-notice" role="alert">{failureMessage(accept.error)}</div>}</div>{editing && sourceDraftId && <PlanEditor key={`${sourceDraftId}-${unit}`} draftId={sourceDraftId} data={detail.data} unit={unit} onSaved={onDraft} onCancel={() => setEditing(false)} />}<PlanChart data={detail.data} unit={unit} /></section>;
}
