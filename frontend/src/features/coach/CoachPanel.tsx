import { motion } from 'framer-motion';
import { useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useCoachConfirm, useCoachMessages, useCoachSend } from './coach';
import type { CoachMessage } from './coach';
import './coach.css';

function ProposalPreview({ message }: { message: CoachMessage }) {
  const proposal = message.proposal;
  if (!proposal) return null;
  const pending = message.proposal_state === 'pending';
  return <div className="coach-proposal" aria-label="Proposed change">
    <strong>{proposal.kind.replaceAll('_', ' ')} proposal</strong>
    <p>{proposal.summary}</p>
    <details><summary>Show exact changes</summary><pre>{JSON.stringify(proposal.payload, null, 2)}</pre></details>
    {pending && <ConfirmProposal messageId={message.id} />}
    {message.proposal_state === 'confirmed' && <p className="coach-confirmed" role="status">Change confirmed and saved.</p>}
    {message.proposal_state === 'expired' && <p className="coach-expired" role="status">This proposal is stale. Ask the coach for a fresh proposal.</p>}
  </div>;
}
function ConfirmProposal({ messageId }: { messageId: string }) {
  const confirm = useCoachConfirm();
  return <button className="coach-confirm" type="button" disabled={confirm.isPending} onClick={() => { void confirm.mutateAsync(messageId).catch(() => undefined); }}>
    {confirm.isPending ? 'Saving…' : 'Confirm and save this exact change'}
  </button>;
}
function MessageBubble({ message }: { message: CoachMessage }) {
  return <article className={`coach-message coach-message-${message.role}`}>
    <div className="coach-message-label">{message.role === 'user' ? 'You' : 'Coach'}</div>
    <p>{message.content}</p>
    {message.status === 'unavailable' && <small>AI is unavailable right now. No logged data was changed.</small>}
    <ProposalPreview message={message} />
  </article>;
}

/** Floating authenticated coach panel. Mount once inside the authenticated shell. */
export function CoachPanel() {
  const heading = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const historyRef = useRef<HTMLDivElement>(null);
  const messages = useCoachMessages(offset);
  const send = useCoachSend();
  const conversationId = messages.data?.conversation_id ?? null;
  useEffect(() => {
    if (!open || offset !== 0 || !historyRef.current) return;
    historyRef.current.scrollTo({
      top: historyRef.current.scrollHeight,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
  }, [open, offset, messages.data?.items.at(-1)?.id, pendingMessage]);
  function submit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || send.isPending) return;
    setPendingMessage(message);
    void send.mutateAsync({ message, conversationId })
      .then(() => { setDraft(''); setOffset(0); })
      .catch(() => undefined)
      .finally(() => setPendingMessage(null));
  }
  return <aside className={`coach-panel ${open ? 'coach-panel-open' : ''}`} aria-labelledby={heading}>
    <button className="coach-launcher" type="button" aria-expanded={open} aria-controls={heading} onClick={() => setOpen((value) => !value)}>
      {open ? 'Close coach' : 'Open coach'}
    </button>
    {open && <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className="coach-window">
      <header><h2 id={heading}>KINETIX coach</h2><p>Private guidance from your logged training and nutrition.</p></header>
      <div ref={historyRef} className="coach-history" aria-live="polite">
        {messages.isError && <p className="coach-error">Conversation unavailable. Try again.</p>}
        {messages.data?.items.length === 0 && <p className="coach-muted">Ask about your current plan, workouts, or meals.</p>}
        {messages.data?.items.map((message) => <MessageBubble key={message.id} message={message} />)}
        {pendingMessage && <><article className="coach-message coach-message-user"><div className="coach-message-label">You</div><p>{pendingMessage}</p></article><p className="coach-message coach-message-coach coach-pending" role="status">Waiting for a validated coach response. Your conversation is saved; no proposed change is applied before you confirm it.</p></>}
      </div>
      {messages.data && messages.data.total > 30 && <div className="coach-pagination">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>Newer</button>
        <span>{offset + 1}–{Math.min(offset + 30, messages.data.total)} of {messages.data.total}</span>
        <button type="button" disabled={offset + 30 >= messages.data.total} onClick={() => setOffset(offset + 30)}>Older</button>
      </div>}
      <form className="coach-compose" onSubmit={submit}>
        <label htmlFor={`${heading}-input`}>Message the coach</label>
        <textarea id={`${heading}-input`} value={draft} maxLength={4000} rows={3} disabled={send.isPending} placeholder="Ask for guidance or a proposed change…" onChange={(event) => setDraft(event.target.value)} />
        <button className="coach-send" type="submit" disabled={send.isPending || !draft.trim()}>{send.isPending ? 'Thinking…' : 'Send'}</button>
        {send.isError && <small className="coach-error">No coach response was received. Your message may have been saved; conversation history is being refreshed.</small>}
      </form>
    </motion.section>}
  </aside>;
}
