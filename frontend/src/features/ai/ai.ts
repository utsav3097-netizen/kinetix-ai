import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { api, authSession } from '../../lib/api';
import type { ApiOptions } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

const text = z.string().min(1).max(8000);
const metric = z.number().finite().nonnegative();
const nutrientsSchema = z.object({ calories_kcal: metric, protein_g: metric, carbs_g: metric, fat_g: metric, fiber_g: metric });
const foodSnapshotSchema = z.object({ name: text, basis_grams: z.literal(100), calories: metric, protein_g: metric, carbs_g: metric, fat_g: metric, fiber_g: metric });
export const setInsightSchema = z.object({ summary: text, form_cue: text, tempo_cue: text, next_action: text, disclaimer: text }).strict();
export const parsedMealSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), training_day: z.boolean(), title: z.string().min(1).max(120),
  slot: z.enum(['breakfast', 'pre_workout', 'post_workout', 'lunch', 'dinner', 'snacks']), time: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/),
  items: z.array(z.object({ label: text, food_id: z.string().min(1).nullable(), grams: z.number().finite().positive().max(5000).nullable(), food_snapshot: foodSnapshotSchema.nullable(), nutrients: nutrientsSchema.nullable(), resolution: z.enum(['resolved', 'unresolved']), reason: text.nullable() }).strict().refine((item) => item.resolution !== 'resolved' || (item.food_id !== null && item.grams !== null && item.food_snapshot !== null && item.nutrients !== null), 'Resolved items must include a food and measured quantity.')).min(1).max(50),
  totals: nutrientsSchema,
}).strict();
const comparisonSchema = z.object({ estimated_1rm_kg: metric.nullable(), previous_estimated_1rm_kg: metric.nullable(), one_rm_change_kg: z.number().finite().nullable(), volume_kg: metric.nullable(), previous_volume_kg: metric.nullable(), volume_change_kg: z.number().finite().nullable(), comparison_basis: text });
const insightSchema = z.object({
  id: z.string().min(1), kind: z.enum(['set', 'exercise_block', 'meal_parse']), status: z.enum(['pending', 'success', 'unavailable']),
  result: z.union([setInsightSchema, parsedMealSchema]).nullable(), reason: text.nullable(), provider: text.nullable(), model: text.nullable(),
  created_at: z.string(), finished_at: z.string().nullable(), latency_ms: z.number().finite().nonnegative().nullable(), comparison: comparisonSchema.nullable(),
}).superRefine((value, context) => {
  if (value.status === 'success' && !(value.kind === 'meal_parse' ? parsedMealSchema : setInsightSchema).safeParse(value.result).success) context.addIssue({ code: 'custom', message: 'AI returned an invalid result.' });
  if (value.status !== 'success' && value.result !== null) context.addIssue({ code: 'custom', message: 'AI result is not ready.' });
});
export type InsightView = z.infer<typeof insightSchema>;
export type SetInsight = z.infer<typeof setInsightSchema>;
export type ParsedMealDraft = z.infer<typeof parsedMealSchema>;
export type InsightNamespace = 'workouts' | 'nutrition';
export const aiKeys = { insight: (owner: string | undefined, namespace: InsightNamespace, id: string | null) => ['ai', owner, namespace, id] as const };
function assertAccount(owner: string | undefined) {
  if (!owner || authSession.getUser()?.id !== owner) throw new Error('Your account changed. Reopen this page before continuing.');
}
function validateInsight(value: unknown, namespace: InsightNamespace) {
  const parsed = insightSchema.safeParse(value);
  if (!parsed.success || (parsed.data.kind === 'meal_parse') !== (namespace === 'nutrition')) throw new Error('AI analysis unavailable: the response could not be validated. Your logged data is unchanged.');
  return parsed.data;
}
export function useInsight(namespace: InsightNamespace, id: string | null) {
  const { user } = useAuth();
  const owner = user?.id;
  return useQuery({
    queryKey: aiKeys.insight(owner, namespace, id), enabled: Boolean(owner && id), retry: false,
    queryFn: async ({ signal }) => { assertAccount(owner); const value = await api<unknown>(`/${namespace}/insights/${encodeURIComponent(id!)}`, { signal }); assertAccount(owner); return validateInsight(value, namespace); },
    refetchInterval: (query) => query.state.status !== 'error' && query.state.data?.status === 'pending' ? 1500 : false,
    refetchIntervalInBackground: false, refetchOnWindowFocus: (query) => query.state.data?.status === 'pending',
    staleTime: Infinity,
  });
}
export function useRequestInsight(namespace: InsightNamespace) {
  const { user } = useAuth();
  const owner = user?.id;
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async ({ path, input }: { path: string; input?: ApiOptions['json'] }) => { assertAccount(owner); const value = await api<unknown>(path, { method: 'POST', json: input }); assertAccount(owner); return validateInsight(value, namespace); },
    onSuccess: (value) => { if (authSession.getUser()?.id === owner) client.setQueryData(aiKeys.insight(owner, namespace, value.id), value); },
  });
}
