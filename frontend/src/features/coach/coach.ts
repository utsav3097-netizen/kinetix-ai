import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, authSession } from '../../lib/api';
import type { ApiOptions } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

export type CoachProposal = {
  kind: 'plan_draft' | 'plan_edit' | 'workout_update' | 'meal_update';
  target_id: string | null;
  summary: string;
  expected_revision?: number | null;
  payload: Record<string, unknown>;
};
export type CoachMessage = {
  id: string;
  role: 'user' | 'assistant';
  status: 'complete' | 'unavailable' | 'safety';
  content: string;
  proposal_state: 'none' | 'pending' | 'confirmed' | 'expired' | 'rejected';
  proposal: CoachProposal | null;
  result: Record<string, unknown> | null;
  created_at: string;
  confirmed_at: string | null;
};
export type CoachPage = { conversation_id: string | null; items: CoachMessage[]; total: number };
export type CoachSendResponse = { conversation_id: string; user: CoachMessage; assistant: CoachMessage };
export type CoachConfirmation = { message: CoachMessage; committed: boolean };

const PAGE_SIZE = 30;
export const coachKeys = { all: (userId: string | undefined) => ['coach', userId] as const };
function assertAccount(userId: string | undefined) {
  if (!userId || authSession.getUser()?.id !== userId) throw new Error('Your account changed. Reopen the coach before continuing.');
}
function useCoachRequest<T>(path: string, enabled = true) {
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({
    queryKey: [...coachKeys.all(userId), path],
    enabled: Boolean(userId) && enabled,
    queryFn: async ({ signal }) => { assertAccount(userId); const result = await api<T>(path, { signal }); assertAccount(userId); return result; },
  });
}
export function useCoachMessages(offset = 0) {
  return useCoachRequest<CoachPage>(`/coach/messages?offset=${offset}&limit=${PAGE_SIZE}`);
}
export function useCoachSend() {
  const { user } = useAuth();
  const userId = user?.id;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ message, conversationId }: { message: string; conversationId?: string | null }) => {
      assertAccount(userId);
      const result = await api<CoachSendResponse>('/coach/messages', { method: 'POST', json: { message, conversation_id: conversationId ?? undefined }, timeoutMs: 185_000 });
      assertAccount(userId);
      return result;
    },
    onSuccess: () => { if (authSession.getUser()?.id === userId) void client.invalidateQueries({ queryKey: coachKeys.all(userId) }); },
    // The server commits the user turn before contacting providers. If the
    // browser/network loses the response, reload history rather than claiming
    // that nothing was saved.
    onError: () => { if (authSession.getUser()?.id === userId) void client.invalidateQueries({ queryKey: coachKeys.all(userId) }); },
  });
}
export function useCoachConfirm() {
  const { user } = useAuth();
  const userId = user?.id;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (messageId: string) => {
      assertAccount(userId);
      const result = await api<CoachConfirmation>(`/coach/messages/${encodeURIComponent(messageId)}/confirm`, { method: 'POST', json: { confirm: true } as ApiOptions['json'] });
      assertAccount(userId);
      return result;
    },
    onSuccess: () => { if (authSession.getUser()?.id === userId) void Promise.all([client.invalidateQueries({ queryKey: coachKeys.all(userId) }), client.invalidateQueries({ queryKey: ['planning', userId] }), client.invalidateQueries({ queryKey: ['workouts', userId] }), client.invalidateQueries({ queryKey: ['nutrition', userId] })]); },
  });
}
