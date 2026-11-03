import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, authSession } from '../../lib/api';
import type { ApiOptions } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import type { Analytics, BlockView, Page } from '../workouts/workouts';
import type { FoodSnapshot, MacroTargets, Nutrients, NutritionTrends } from '../nutrition/nutrition';
import { utcToday } from '../profile/profile';

export type PlanPath = 'cutting' | 'bulking' | 'recomp' | 'powerbuilding' | 'classic_physique' | 'athletic_hybrid';
export type PathOptions = { items: { id: PlanPath; title: string; phase: string; description: string; evidence: string; assessment_required: boolean }[]; history_sufficient: boolean; report_id: string | null };
export type ReportSummary = { id: string; kind: 'weekly' | 'analysis' | 'snapshot'; window_start: string; window_end: string; created_at: string; revision: number; macro_adherence_score: number | null; logged_training_days: number; logged_nutrition_days: number; expected_days: number };
export type ReportView = ReportSummary & { data: { total_sessions: number; total_volume_kg: number; muscles: Analytics['muscles']; strength_curves: Analytics['strength_curves']; weight_points: { date: string; weight_kg: number }[]; nutrition: NutritionTrends; fatigue: Analytics['fatigue']; source_record_ids: string[]; history_sufficient: boolean; explanation: string } };
export type PlanExercise = { exercise_id: string; exercise_snapshot: BlockView['exercise_snapshot']; sets: number; target_min_reps: number | null; target_max_reps: number | null; duration_seconds: number | null; external_load_kg: number; effective_load_kg: number; rest_seconds: number; progression: BlockView['progression'] | null; observed_1rm_kg: number | null; observed_velocity_kg_per_week: number | null; rationale: string };
export type SampleMeal = { slot: string; title: string; items: { food_id: string; grams: number; food_snapshot: FoodSnapshot; nutrients: Nutrients }[]; totals: Nutrients };
export type PlanDay = { date: string; training_day: boolean; label: string; exercises: PlanExercise[]; targets: MacroTargets; sample_meals: SampleMeal[]; sample_totals: Nutrients };
export type PlanData = { path: PlanPath; title: string; assessment_required: boolean; explanation: string; profile_snapshot: { bodyweight_kg: number; tdee_kcal: number; phase: string }; evidence: { report_id: string | null; training_days: number; notes: string[] }; days: PlanDay[] };
export type DraftSummary = { id: string; path: PlanPath; title: string; starts_on: string; ends_on: string; assessment_required: boolean; created_at: string; parent_version_id: string | null; based_on_draft_id: string | null };
export type DraftView = DraftSummary & { data: PlanData };
export type VersionSummary = { id: string; version: number; draft_id: string; accepted_at: string; title: string; path: PlanPath; starts_on: string; ends_on: string };
export type VersionView = VersionSummary & { data: PlanData };
export type PlanEditInput = { title: string; days: { date: string; training_day: boolean; label: string; exercises: Pick<PlanExercise, 'exercise_id' | 'sets' | 'target_min_reps' | 'target_max_reps' | 'duration_seconds' | 'external_load_kg' | 'rest_seconds'>[]; protein_g: number; carbs_g: number; fat_g: number }[] };
export const PLAN_PAGE_SIZE = 10;
export const planningKeys = { all: (userId: string | undefined) => ['planning', userId] as const };
function assertAccount(userId: string | undefined) {
  if (!userId || authSession.getUser()?.id !== userId) throw new Error('Your account changed. Reopen reports and plans before continuing.');
}
function usePlanningQuery<T>(path: string, enabled = true) {
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({ queryKey: [...planningKeys.all(userId), path], enabled: Boolean(userId) && enabled,
    queryFn: async ({ signal }) => { assertAccount(userId); const result = await api<T>(path, { signal }); assertAccount(userId); return result; },
  });
}
export const useReports = (offset: number) => usePlanningQuery<Page<ReportSummary>>(`/reports?offset=${offset}&limit=${PLAN_PAGE_SIZE}`);
export const useReport = (id: string) => usePlanningQuery<ReportView>(`/reports/${encodeURIComponent(id)}`, Boolean(id));
export const usePaths = () => usePlanningQuery<PathOptions>('/plans/paths');
export const useDrafts = (offset: number) => usePlanningQuery<Page<DraftSummary>>(`/plans/drafts?offset=${offset}&limit=${PLAN_PAGE_SIZE}`);
export const useVersions = (offset: number) => usePlanningQuery<Page<VersionSummary>>(`/plans/versions?offset=${offset}&limit=${PLAN_PAGE_SIZE}`);
export const useDraft = (id: string) => usePlanningQuery<DraftView>(`/plans/drafts/${encodeURIComponent(id)}`, Boolean(id));
export const useVersion = (id: string) => usePlanningQuery<VersionView>(`/plans/versions/${encodeURIComponent(id)}`, Boolean(id));
export const useActivePlan = () => usePlanningQuery<VersionView | null>('/plans/active');
export function usePlanningMutation<T>() {
  const { user } = useAuth();
  const userId = user?.id;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ path, input }: { path: string; input: ApiOptions['json'] }) => {
      assertAccount(userId);
      const result = await api<T>(path, { method: 'POST', json: input });
      assertAccount(userId);
      return result;
    },
    onSuccess: async () => {
      if (authSession.getUser()?.id !== userId) return;
      await Promise.all(['planning', 'athlete', 'nutrition', 'dashboard'].map((key) => client.invalidateQueries({ queryKey: [key, userId] })));
    },
  });
}
export function upcomingMonday() {
  const date = new Date(`${utcToday()}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + ((8 - date.getUTCDay()) % 7 || 7));
  return date.toISOString().slice(0, 10);
}
