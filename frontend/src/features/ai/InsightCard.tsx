import { useId, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { failureMessage } from '../nutrition/nutrition';
import { numberText, weightText } from '../workouts/workouts';
import type { Unit } from '../workouts/workouts';
import { setInsightSchema, useInsight, useRequestInsight } from './ai';
import type { InsightView } from './ai';
import './ai.css';

export function InsightCard({ insight, loading = false, error, onRetry, retrying = false, title = 'AI analysis', unit = 'kg' }: { insight?: InsightView; loading?: boolean; error?: unknown; onRetry?: () => void; retrying?: boolean; title?: string; unit?: Unit }) {
  const heading = useId();
  const result = insight?.status === 'success' && insight.kind !== 'meal_parse' ? setInsightSchema.safeParse(insight.result) : null;
  const comparison = insight?.comparison;
  const weight = (value: number | null) => value === null ? 'Not available' : weightText(value, unit);
  const volume = (value: number | null) => value === null ? 'Not available' : `${numberText(value)} kg·reps`;
  return <section className="ai-insight" aria-labelledby={heading} aria-busy={loading || retrying || insight?.status === 'pending'}>
    <h5 id={heading}>{title}</h5>
    <div role="status" aria-live="polite">
      {error ? <p className="error-notice">AI analysis unavailable. {failureMessage(error)}</p> : loading || retrying || insight?.status === 'pending' ? <p>AI analysis pending. You can keep logging while the queued analysis finishes.</p> : insight?.status === 'unavailable' ? <p>AI analysis unavailable. {insight.reason ?? 'The providers could not return a validated result.'}</p> : insight?.status === 'success' ? <p className="ai-attribution">AI-generated · {insight.provider ?? 'Provider not reported'}{insight.model ? ` · ${insight.model}` : ''}</p> : <p>No AI analysis requested for this saved record.</p>}
    </div>
    {comparison && <div className="ai-comparison"><h6>Observed comparison · deterministic</h6><dl className="ai-comparison-grid"><div><dt>Current estimated 1RM</dt><dd>{weight(comparison.estimated_1rm_kg)}</dd></div><div><dt>Previous estimated 1RM</dt><dd>{weight(comparison.previous_estimated_1rm_kg)}</dd></div><div><dt>Estimated 1RM change</dt><dd>{weight(comparison.one_rm_change_kg)}</dd></div><div><dt>Current rep-volume</dt><dd>{volume(comparison.volume_kg)}</dd></div><div><dt>Previous rep-volume</dt><dd>{volume(comparison.previous_volume_kg)}</dd></div><div><dt>Rep-volume change</dt><dd>{volume(comparison.volume_change_kg)}</dd></div></dl><p className="measurement-note">{comparison.comparison_basis}</p></div>}
    {result?.success && <><p>{result.data.summary}</p><dl className="ai-cues"><div><dt>General form cue</dt><dd>{result.data.form_cue}</dd></div><div><dt>Tempo cue</dt><dd>{result.data.tempo_cue}</dd></div><div><dt>Next action</dt><dd>{result.data.next_action.replaceAll('_', ' ')}</dd></div></dl><p className="measurement-note">{result.data.disclaimer}</p></>}
    <p className="measurement-note">AI does not change your saved metrics, progression targets, or entries.</p>
    {onRetry && <button className="secondary-button" type="button" disabled={retrying || loading || insight?.status === 'pending'} onClick={onRetry}>{retrying ? 'Requesting analysis…' : error ? 'Check analysis again' : insight?.status === 'unavailable' ? 'Retry AI analysis' : 'Analyze saved record'}</button>}
  </section>;
}

function OwnedWorkoutInsight({ insightId, analyzePath, title, unit }: { insightId: string | null; analyzePath: string; title: string; unit: Unit }) {
  const [requestedId, setRequestedId] = useState<string | null>(null);
  const query = useInsight('workouts', requestedId ?? insightId);
  const request = useRequestInsight('workouts');
  async function analyze() {
    try { const value = await request.mutateAsync({ path: analyzePath }); setRequestedId(value.id); }
    catch { /* The card displays the request failure. */ }
  }
  const hasId = Boolean(requestedId ?? insightId);
  return <InsightCard insight={query.data} loading={hasId && query.isPending} error={query.error ?? request.error} retrying={request.isPending} title={title} unit={unit} onRetry={query.isError ? () => void query.refetch() : !query.data || query.data.status === 'unavailable' ? () => void analyze() : undefined} />;
}

export function WorkoutInsight(props: { insightId: string | null; analyzePath: string; title: string; unit: Unit; sourceKey: string }) {
  const { user } = useAuth();
  return <OwnedWorkoutInsight key={`${user?.id}-${props.sourceKey}-${props.insightId}`} {...props} />;
}
