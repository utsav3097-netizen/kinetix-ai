import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { profileKeys, useProfile } from '../profile/profile';
import type { Profile } from '../profile/profile';

export type DashboardTargets = {
  bmr_kcal: number;
  tdee_kcal: number;
  phase: Profile['phase'];
  training_day: boolean;
  plan_version_id?: string | null;
  macros: {
    calories_kcal: number;
    base_calories_kcal: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
    carb_cycle_factor: number;
  };
  protein_range_g: { min: number; max: number };
  disclaimer: string;
};

export const targetKeys = {
  day: (userId: string | undefined, trainingDay: boolean | null) =>
    [...profileKeys.all(userId), 'dashboard-targets', { training_day: trainingDay }] as const,
};

export function useDashboardTargets(trainingDay: boolean | null) {
  const { user } = useAuth();
  const profile = useProfile();
  return useQuery({
    queryKey: targetKeys.day(user?.id, trainingDay),
    queryFn: ({ signal }) => api<DashboardTargets>(`/dashboard/targets${trainingDay === null ? '' : `?training_day=${trainingDay}`}`, { signal }),
    enabled: Boolean(user && profile.data?.onboarding_complete && profile.data.profile),
  });
}
