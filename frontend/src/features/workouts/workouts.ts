import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, authSession } from '../../lib/api';
import type { ApiOptions } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import type { ExerciseInput } from '../library/reference';

export type Unit = 'kg' | 'lb';
export const LB_PER_KG = 2.2046226218;
export const toKg = (value: number, unit: Unit) => unit === 'lb' ? value / LB_PER_KG : value;
export const fromKg = (value: number, unit: Unit) => unit === 'lb' ? value * LB_PER_KG : value;
export const numberText = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });
export const weightText = (value: number, unit: Unit) => `${numberText(fromKg(value, unit))} ${unit}`;
export const PAGE_SIZE = 10;
export type Page<T> = { items: T[]; total: number };
export type SessionInput = { title: string; performed_on: string; bodyweight_kg: number; sleep_hours: number | null; soreness: number | null };
export type SessionSummary = { id: string; title: string; performed_on: string; bodyweight_kg: number; total_volume_kg: number; exercise_count: number; set_count: number; revision: number };
export type SetInput = { ordinal: number; set_type: 'warmup' | 'working' | 'drop_set' | 'failure'; external_load_kg: number; repetitions: number | null; duration_seconds: number | null; rpe: number | null; rir: number | null; rest_seconds: number };
export type SetView = SetInput & { id: string; source_record_id: string; insight_id: string | null; bodyweight_kg: number; metrics: { effective_load_kg: number; volume_kg: number | null; estimated_1rm_kg: number | null; one_rm_formula: 'epley' | 'brzycki' | null; estimate_unavailable_reason: string | null } };
export type BlockInput = { ordinal: number; target_min_reps: number; target_max_reps: number };
export type BlockView = BlockInput & { id: string; insight_id: string | null; exercise_id: string; exercise_snapshot: Pick<ExerciseInput, 'name' | 'equipment' | 'biomechanical_multiplier' | 'classification' | 'measurement_type' | 'muscles'>; completed: boolean; sets: SetView[]; progression: { state: string; next_weight_kg: number; target_reps: number; reason: string; recovery_check: boolean } };
export type SessionView = SessionSummary & { sleep_hours: number | null; soreness: number | null; exercises: BlockView[] };
export type SourceRecord = { id: string; revision: number; entity_type: string; entity_id: string; action: string; payload: unknown; created_at: string };
export type ExerciseHistoryEntry = { session_id: string; performed_on: string; set: SetView };
export type Analytics = { weeks: number; total_sessions: number; total_volume_kg: number; muscles: { id: string; name: string; hard_sets: number; weekly_hard_sets: number; volume_kg: number; landmark: string; recovery_warning: boolean }[]; strength_curves: { exercise_id: string; name: string; points: { date: string; estimated_1rm_kg: number; volume_kg: number }[] }[]; prs: { exercise_id: string; name: string; estimated_1rm_kg: number; performed_on: string }[]; fatigue: { state: 'available' | 'unavailable'; score: number | null; missing_inputs: string[]; components: Record<string, number>; disclaimer: string } };
export const workoutKeys = { all: (userId: string | undefined) => ['workouts', userId] as const };

function assertAccount(userId: string | undefined) {
  if (!userId || authSession.getUser()?.id !== userId) throw new Error('Your account changed. Reopen workouts before continuing.');
}
function useWorkoutQuery<T>(path: string, enabled = true) {
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({
    queryKey: [...workoutKeys.all(userId), path],
    enabled: Boolean(userId) && enabled,
    queryFn: async ({ signal }) => {
      assertAccount(userId);
      const response = await api<T>(path, { signal });
      assertAccount(userId);
      return response;
    },
  });
}
export function useSessions(offset: number, from: string, to: string) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(PAGE_SIZE) });
  if (from) params.set('from_date', from);
  if (to) params.set('to_date', to);
  return useWorkoutQuery<Page<SessionSummary>>(`/workouts?${params}`);
}
export const sessionPath = (id: string) => `/workouts/${encodeURIComponent(id)}`;
export const blockPath = (sessionId: string, blockId: string) => `${sessionPath(sessionId)}/exercises/${encodeURIComponent(blockId)}`;
export function useSession(id: string) { return useWorkoutQuery<SessionView>(sessionPath(id), Boolean(id)); }
export function useWorkoutAnalytics(weeks: number) { return useWorkoutQuery<Analytics>(`/workouts/analytics?weeks=${weeks}`); }
export function useSourceHistory(id: string, offset: number) { return useWorkoutQuery<Page<SourceRecord>>(`${sessionPath(id)}/history?offset=${offset}&limit=${PAGE_SIZE}`); }
export function useExerciseHistory(id: string, offset: number) { return useWorkoutQuery<Page<ExerciseHistoryEntry>>(`/workouts/exercise-history/${encodeURIComponent(id)}?offset=${offset}&limit=${PAGE_SIZE}`); }
export function useWorkoutMutation() {
  const { user } = useAuth();
  const userId = user?.id;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ path, method, input }: { path: string; method: 'POST' | 'PUT' | 'DELETE'; input?: ApiOptions['json'] }) => {
      assertAccount(userId);
      const result = await api<SessionView | undefined>(path, { method, json: input });
      assertAccount(userId);
      return result;
    },
    onSuccess: async () => {
      if (authSession.getUser()?.id !== userId) return;
      await client.invalidateQueries({ queryKey: workoutKeys.all(userId) });
    },
  });
}
