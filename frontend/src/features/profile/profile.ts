import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { api, authSession } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

export const phaseLabels = {
  baseline_assessment: 'Baseline assessment',
  cutting: 'Cutting',
  lean_bulking: 'Lean bulking',
  body_recomposition: 'Body recomposition',
  calisthenics_strength: 'Calisthenics and strength',
} as const;

export const profileSchema = z.object({
  full_name: z.string().trim().min(1, 'Enter your full name.').max(120),
  nickname: z.string().trim().min(1, 'Enter a nickname.').max(40),
  age: z.number('Enter your age.').int('Use a whole number.').min(13).max(100),
  biological_sex: z.enum(['male', 'female'], 'Select biological sex for the BMR formula.'),
  height_cm: z.number('Enter height in cm.').finite().min(50).max(250),
  starting_weight_kg: z.number('Enter starting weight in kg.').finite().min(20).max(500),
  current_weight_kg: z.number('Enter current weight in kg.').finite().min(20).max(500),
  body_fat_percentage: z.number('Enter a percentage or leave blank.').finite().min(1).max(75).nullable(),
  display_unit: z.enum(['kg', 'lb']),
  activity_multiplier: z.number('Enter an activity multiplier.').finite().min(1.2).max(2.4),
  phase: z.enum(['baseline_assessment', 'cutting', 'lean_bulking', 'body_recomposition', 'calisthenics_strength']),
  analysis_weeks: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)], 'Choose 1, 2, 3, or 4 weeks.'),
});
export type ProfileInput = z.infer<typeof profileSchema>;
export type Profile = ProfileInput & { user_id: string; created_at: string; updated_at: string };
export type ProfileResponse = { onboarding_complete: boolean; profile: Profile | null };
export type WeightCheckIn = { id: string; measured_on: string; weight_kg: number };
export type WeightHistory = { items: WeightCheckIn[]; total: number };
export const utcToday = () => new Date().toISOString().slice(0, 10);
export const checkInSchema = z.object({
  measured_on: z.iso.date('Enter a valid measurement date.'),
  weight_kg: z.number('Enter weight in kg.').finite().min(20).max(500),
});
export type CheckInInput = z.infer<typeof checkInSchema>;
export const profileKeys = {
  all: (userId: string | undefined) => ['athlete', userId] as const,
  profile: (userId: string | undefined) => ['athlete', userId, 'profile'] as const,
  checkIns: (userId: string | undefined) => ['athlete', userId, 'check-ins'] as const,
};

export function useProfile() {
  const { user } = useAuth();
  return useQuery({
    queryKey: profileKeys.profile(user?.id),
    queryFn: ({ signal }) => api<ProfileResponse>('/profile', { signal }),
    enabled: Boolean(user),
  });
}

export function useSaveProfile() {
  const { user } = useAuth();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (profile: ProfileInput) => api<ProfileResponse>('/profile', { method: 'PUT', json: profile }),
    onSuccess: async (response) => {
      if (!user || authSession.getUser()?.id !== user.id) return;
      client.setQueryData(profileKeys.profile(user.id), response);
      await client.invalidateQueries({ queryKey: profileKeys.all(user.id) });
    },
  });
}

export function useWeightCheckIns(offset = 0, limit = 10) {
  const { user } = useAuth();
  return useQuery({
    queryKey: [...profileKeys.checkIns(user?.id), { offset, limit }],
    queryFn: ({ signal }) => api<WeightHistory>(`/profile/check-ins?offset=${offset}&limit=${limit}`, { signal }),
    enabled: Boolean(user),
  });
}

export function useAddWeightCheckIn() {
  const { user } = useAuth();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: CheckInInput) => api<WeightCheckIn>('/profile/check-ins', { method: 'POST', json: input }),
    onSuccess: async () => {
      if (!user || authSession.getUser()?.id !== user.id) return;
      await client.invalidateQueries({ queryKey: profileKeys.all(user.id) });
    },
  });
}

export function formatWeight(kg: number, unit: ProfileInput['display_unit']) {
  return `${(unit === 'lb' ? kg * 2.2046226218 : kg).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${unit}`;
}
