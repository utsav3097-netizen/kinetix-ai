import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { api, ApiError, authSession } from '../../lib/api';
import type { ApiOptions } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { referenceKeys } from '../library/reference';
import type { CatalogPage, Food } from '../library/reference';

export const mealSlotLabels = { breakfast: 'Breakfast', pre_workout: 'Pre-workout', post_workout: 'Post-workout', lunch: 'Lunch', dinner: 'Dinner', snacks: 'Snacks' } as const;
export const mealSchema = z.object({
  training_day: z.boolean(),
  slot: z.enum(['breakfast', 'pre_workout', 'post_workout', 'lunch', 'dinner', 'snacks']),
  title: z.string().trim().min(1, 'Enter a meal title.').max(120),
  time: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Choose a valid meal time.'),
  items: z.array(z.object({ food_id: z.string().min(1), grams: z.number().finite().positive('Consumed grams must be greater than zero.').max(5000), item_id: z.string().nullable().optional() })).min(1, 'Add at least one food.').max(50),
});
export type MealInput = z.infer<typeof mealSchema>;
export type Nutrients = { calories_kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number };
export type FoodSnapshot = { name: string; basis_grams: 100; calories: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number };
export type MacroTargets = { calories_kcal: number; base_calories_kcal: number; protein_g: number; carbs_g: number; fat_g: number; carb_cycle_factor: number };
export type MealItem = { id: string; food_id: string; grams: number; food_snapshot: FoodSnapshot; nutrients: Nutrients };
export type MealView = { id: string; date: string; slot: MealInput['slot']; title: string; time: string; items: MealItem[]; totals: Nutrients; source_record_id: string };
export type MealDraft = Pick<MealInput, 'title' | 'slot' | 'time'> & { items: { food_id: string; grams: number; item_id?: string; food_snapshot: FoodSnapshot }[] };
export type WaterView = { id: string; amount_ml: number; created_at: string };
export type AdherenceStatus = 'below' | 'within' | 'above' | 'unlogged';
export type NutrientAdherence = { actual: number; target: number; status: AdherenceStatus; score: number | null };
export type Adherence = {
  macro_score: number | null;
  protein: { actual_g: number; min_g: number; max_g: number; status: AdherenceStatus; score: number | null };
  calories: NutrientAdherence; carbs: NutrientAdherence; fat: NutrientAdherence;
  caloric_drift_kcal: number | null;
  protein_timing: { status: 'available' | 'insufficient_data'; gaps: { from_time: string; to_time: string; hours: number }[] };
};
export type NutritionDay = { date: string; training_day: boolean; persisted: boolean; phase: string; plan_version_id?: string | null; bodyweight_kg: number; targets: MacroTargets; protein_range_g: { min: number; max: number }; totals: Nutrients & { water_ml: number }; meals: MealView[]; water_entries: WaterView[]; adherence: Adherence };
export type NutritionSourceRecord = { id: string; revision: number; entity_type: string; entity_id: string; action: string; payload: unknown; created_at: string };
export type NutritionTrendPoint = { date: string; logged: boolean; calories_kcal: number | null; target_calories_kcal: number | null; protein_g: number | null; carbs_g: number | null; fat_g: number | null; macro_score: number | null };
export type NutritionTrends = { window_start: string; window_end: string; logged_days: number; expected_days: number; coverage_percent: number; averages: Nutrients | null; macro_adherence_score: number | null; caloric_drift_kcal: number | null; protein_timing_gap_count: number; points: NutritionTrendPoint[] };
export const HISTORY_PAGE_SIZE = 20;
export const nutritionKeys = { all: (userId: string | undefined) => ['nutrition', userId] as const };
export const dayPath = (date: string) => `/nutrition/days/${encodeURIComponent(date)}`;
export const mealPath = (id: string) => `/nutrition/meals/${encodeURIComponent(id)}`;
export const waterPath = (id: string) => `/nutrition/water/${encodeURIComponent(id)}`;
export const numberText = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 });
export const scoreText = (value: number | null) => value === null ? 'Not available' : `${numberText(value)} / 100`;
export const driftText = (value: number | null) => value === null ? 'Not available' : `${value > 0 ? '+' : ''}${numberText(value)} kcal`;
export function failureMessage(error: unknown) {
  if (error instanceof ApiError) return [error.message, ...Object.values(error.fieldErrors)].join(' ');
  return error instanceof Error ? error.message : 'Could not save your changes. Please try again.';
}
export function assertNutritionAccount(userId: string | undefined) {
  if (!userId || authSession.getUser()?.id !== userId) throw new Error('Your account changed. Reopen nutrition before continuing.');
}
function useNutritionQuery<T>(path: string) {
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({
    queryKey: [...nutritionKeys.all(userId), path], enabled: Boolean(userId),
    queryFn: async ({ signal }) => { assertNutritionAccount(userId); const result = await api<T>(path, { signal }); assertNutritionAccount(userId); return result; },
  });
}
export function useNutritionDay(date: string) { return useNutritionQuery<NutritionDay>(dayPath(date)); }
export function useNutritionTrends(weeks: number, endDate: string) { return useNutritionQuery<NutritionTrends>(`/nutrition/trends?weeks=${weeks}&end_date=${encodeURIComponent(endDate)}`); }
export function useNutritionHistory(date: string, offset: number) { return useNutritionQuery<{ items: NutritionSourceRecord[]; total: number }>(`${dayPath(date)}/history?offset=${offset}&limit=${HISTORY_PAGE_SIZE}`); }
export function useNutritionFoods(search: string, offset: number) {
  const { user } = useAuth();
  const userId = user?.id;
  const filters = { q: search, offset, limit: 10 };
  return useQuery({
    queryKey: [...referenceKeys.foods(userId), filters], enabled: Boolean(userId),
    queryFn: async ({ signal }) => { assertNutritionAccount(userId); const result = await api<CatalogPage<Food>>(`/nutrition/foods?${new URLSearchParams({ q: search, offset: String(offset), limit: '10' })}`, { signal }); assertNutritionAccount(userId); return result; },
  });
}
export function useNutritionMutation() {
  const { user } = useAuth();
  const userId = user?.id;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ path, method, input }: { path: string; method: 'POST' | 'PUT' | 'DELETE'; input?: ApiOptions['json'] }) => {
      assertNutritionAccount(userId);
      const result = await api<NutritionDay | undefined>(path, { method, json: input });
      assertNutritionAccount(userId);
      return result;
    },
    onSuccess: async (day) => {
      if (authSession.getUser()?.id !== userId) return;
      if (day) {
        const queryKey = [...nutritionKeys.all(userId), dayPath(day.date)];
        await client.cancelQueries({ queryKey, exact: true });
        if (authSession.getUser()?.id !== userId) return;
        client.setQueryData(queryKey, day);
      }
      await client.invalidateQueries({ queryKey: nutritionKeys.all(userId) });
    },
  });
}
