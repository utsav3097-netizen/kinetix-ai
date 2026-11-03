import { useState } from 'react';
import { CatalogError } from '../library/ReferenceCatalog';
import { NutritionLoading, NutritionPagination } from './NutritionControls';
import { HISTORY_PAGE_SIZE, useNutritionHistory } from './nutrition';

export function NutritionHistory({ date }: { date: string }) {
  const [offset, setOffset] = useState(0);
  const query = useNutritionHistory(date, offset);
  return <section className="connection-card" aria-labelledby="nutrition-history-heading"><h2 id="nutrition-history-heading">Source history · {date}</h2><p>Original entries, corrections, day-type changes, and deletions remain in this append-only journal. Current totals use the latest non-deleted entries.</p>{query.isPending ? <NutritionLoading label="Loading source history…" /> : query.isError ? <CatalogError error={query.error} retry={() => void query.refetch()} /> : <>{query.data.total === 0 ? <p>No saved source records for this date.</p> : <ol className="nutrition-history-list">{query.data.items.map((record) => <li key={record.id}><div className="nutrition-section-heading"><strong>Revision {record.revision} · {record.entity_type.replaceAll('_', ' ')} · {record.action.replaceAll('_', ' ')}</strong><time dateTime={record.created_at}>{new Date(record.created_at).toLocaleString()}</time></div><details><summary>View saved source payload</summary><pre tabIndex={0} aria-label={`Revision ${record.revision} source payload`}>{JSON.stringify(record.payload, null, 2)}</pre></details></li>)}</ol>}<NutritionPagination label="Nutrition source history pages" offset={offset} total={query.data.total} limit={HISTORY_PAGE_SIZE} onChange={setOffset} /></>}</section>;
}
