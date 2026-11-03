import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { api, authSession } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

export const classificationLabels = {
  upper_compound: 'Upper-body compound',
  lower_compound: 'Lower-body compound',
  isolation: 'Isolation',
} as const;

export const exerciseSchema = z.object({
  name: z.string().trim().min(1, 'Enter an exercise name.').max(120),
  equipment: z.string().trim().min(1, 'Enter equipment, or bodyweight.').max(80),
  met: z.number('Enter a MET value.').finite().min(0.1).max(30),
  biomechanical_multiplier: z.number('Enter a biomechanical multiplier.').finite().min(0).max(1),
  measurement_type: z.enum(['reps', 'seconds']),
  classification: z.enum(['upper_compound', 'lower_compound', 'isolation']),
  muscles: z.array(z.object({
    muscle_id: z.string().min(1, 'Choose a muscle.'),
    contribution: z.number('Enter a contribution.').finite().min(0).max(1),
  })).min(1, 'Add at least one muscle.').refine(
    (muscles) => new Set(muscles.map((muscle) => muscle.muscle_id)).size === muscles.length,
    'Choose each muscle only once.',
  ),
});
export const foodSchema = z.object({
  name: z.string().trim().min(1, 'Enter a food name.').max(120),
  calories: z.number('Enter calories per 100 g.').finite().min(0).max(900),
  protein_g: z.number('Enter protein per 100 g.').finite().min(0).max(100),
  carbs_g: z.number('Enter carbohydrate per 100 g.').finite().min(0).max(100),
  fat_g: z.number('Enter fat per 100 g.').finite().min(0).max(100),
  fiber_g: z.number('Enter fiber per 100 g.').finite().min(0).max(100),
}).superRefine((food, context) => {
  if (food.protein_g + food.carbs_g + food.fat_g > 100) {
    context.addIssue({ code: 'custom', path: ['protein_g'], message: 'Protein, carbohydrate, and fat together cannot exceed 100 g.' });
  }
  if (food.fiber_g > food.carbs_g) {
    context.addIssue({ code: 'custom', path: ['fiber_g'], message: 'Fiber cannot exceed total carbohydrate.' });
  }
});
export type ExerciseInput = z.infer<typeof exerciseSchema>;
export type FoodInput = z.infer<typeof foodSchema>;
export type Exercise = ExerciseInput & { id: string; owner_id: string | null; is_custom: boolean };
export type Food = FoodInput & { id: string; owner_id: string | null; is_custom: boolean; basis_grams: 100 };
export type Muscle = { id: string; name: string };
export type CatalogPage<T> = { items: T[]; total: number };
export type FoodFilters = { q?: string; offset?: number; limit?: number };
export type ExerciseFilters = FoodFilters & { muscle?: string; equipment?: string };
export const referenceKeys = {
  all: (userId: string | undefined) => ['reference', userId] as const,
  exercises: (userId: string | undefined) => ['reference', userId, 'exercises'] as const,
  foods: (userId: string | undefined) => ['reference', userId, 'foods'] as const,
};

function queryString(filters: ExerciseFilters) {
  const params = new URLSearchParams({ offset: String(filters.offset ?? 0), limit: String(filters.limit ?? 20) });
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  if (filters.muscle) params.set('muscle', filters.muscle);
  if (filters.equipment?.trim()) params.set('equipment', filters.equipment.trim());
  return params.toString();
}

export function useExercises(filters: ExerciseFilters = {}) {
  const { user } = useAuth();
  return useQuery({
    queryKey: [...referenceKeys.exercises(user?.id), filters],
    queryFn: ({ signal }) => api<CatalogPage<Exercise>>(`/exercises?${queryString(filters)}`, { signal }),
    enabled: Boolean(user),
  });
}
export function useFoods(filters: FoodFilters = {}) {
  const { user } = useAuth();
  return useQuery({
    queryKey: [...referenceKeys.foods(user?.id), filters],
    queryFn: ({ signal }) => api<CatalogPage<Food>>(`/nutrition/foods?${queryString(filters)}`, { signal }),
    enabled: Boolean(user),
  });
}
export function useMuscles() {
  const { user } = useAuth();
  return useQuery({
    queryKey: [...referenceKeys.all(user?.id), 'muscles'],
    queryFn: ({ signal }) => api<Muscle[]>('/exercises/muscles', { signal }),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

function useReferenceMutation<TInput, TRecord>(kind: 'exercises' | 'foods') {
  const { user } = useAuth();
  const client = useQueryClient();
  const path = kind === 'exercises' ? '/exercises' : '/nutrition/foods';
  return useMutation({
    mutationFn: (change: { action: 'save'; id?: string; input: TInput } | { action: 'delete'; id: string }): Promise<TRecord | void> => {
      if (change.action === 'delete') return api<void>(`${path}/${encodeURIComponent(change.id)}`, { method: 'DELETE' });
      return api<TRecord>(change.id ? `${path}/${encodeURIComponent(change.id)}` : path, {
        method: change.id ? 'PUT' : 'POST', json: change.input,
      });
    },
    onSuccess: async () => {
      if (!user || authSession.getUser()?.id !== user.id) return;
      await client.invalidateQueries({ queryKey: referenceKeys[kind](user.id) });
    },
  });
}
export function useExerciseMutation() { return useReferenceMutation<ExerciseInput, Exercise>('exercises'); }
export function useFoodMutation() { return useReferenceMutation<FoodInput, Food>('foods'); }
