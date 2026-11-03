import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { numberText } from './nutrition';

export function NutritionField({ label, children }: { label: string; children: ReactNode }) {
  return <label className="form-field nutrition-field"><span>{label}</span>{children}</label>;
}
export function NutritionLoading({ label }: { label: string }) {
  return <div className="nutrition-loading" role="status" aria-busy="true"><span className="nutrition-skeleton" aria-hidden="true" />{label}</div>;
}
export function NutritionPagination({ offset, total, limit, onChange, label }: { offset: number; total: number; limit: number; onChange: (offset: number) => void; label: string }) {
  if (!total) return null;
  return <nav className="nutrition-pagination" aria-label={label}><button className="secondary-button" type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button><span>{Math.min(offset + 1, total)}–{Math.min(offset + limit, total)} of {total}</span><button className="secondary-button" type="button" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button></nav>;
}
export function DeleteNutritionEntry({ label, detail, pending, onDelete }: { label: string; detail: string; pending: boolean; onDelete: () => Promise<boolean> }) {
  const [confirming, setConfirming] = useState(false);
  const id = useId();
  if (!confirming) return <button type="button" className="text-button danger-text" disabled={pending} onClick={() => setConfirming(true)}>{label}</button>;
  return <div className="nutrition-confirm" role="group" aria-labelledby={id}><p id={id}>{detail} The original source record will remain in history.</p><div className="session-actions"><button className="secondary-button" type="button" disabled={pending} autoFocus onClick={() => setConfirming(false)}>Keep entry</button><button className="secondary-button danger-text" type="button" disabled={pending} onClick={() => void onDelete().then((removed) => { if (removed) setConfirming(false); })}>{pending ? 'Removing…' : 'Confirm removal'}</button></div></div>;
}
export function MacroRing({ label, actual, target, unit, logged }: { label: string; actual: number; target: number; unit: string; logged: boolean }) {
  const id = useId();
  const fraction = target > 0 ? Math.min(actual / target, 1) : 0;
  return <div className="nutrition-macro"><svg viewBox="0 0 100 100" role="img" aria-labelledby={id}><title id={id}>{label}: {logged ? `${numberText(actual)} of ${numberText(target)} ${unit} recorded` : `No meals recorded; target ${numberText(target)} ${unit}`}. Ring caps at the target; exact total is shown.</title><circle className="nutrition-ring-track" cx="50" cy="50" r="42" /><circle className="nutrition-ring-value" cx="50" cy="50" r="42" pathLength="100" strokeDasharray="100" strokeDashoffset={100 - fraction * 100} /><text x="50" y="55" textAnchor="middle" aria-hidden="true">{logged ? numberText(actual) : '—'}</text></svg><strong>{label}</strong><span>{logged ? `${numberText(actual)} / ` : 'Target '}{numberText(target)} {unit}</span></div>;
}
