import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, authSession } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

export type Exercise = { id: string; name: string; equipment: string; met: number; biomechanical_multiplier: number; classification: string; measurement_type: 'reps' | 'seconds'; muscles: { muscle_id: string; contribution: number }[]; is_custom: boolean };
export type Food = { id: string; name: string; basis_grams: number; calories: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number; is_custom: boolean };
export type Setting = { key: string; value: unknown; updated_by?: string; created_at?: string; updated_at?: string };
export type Announcement = { id: string; title: string; body: string; starts_at: string; ends_at: string | null; created_by: string; created_at: string; updated_at: string };
export type Page<T> = { items: T[]; total: number };
export type Analytics = { users: Record<string, number>; onboarding: Record<string, number>; logging: Record<string, number>; ai: Record<string, number | null>; health: Record<string, string | number> };
export type Audit = { id: string; actor_id: string; action: string; resource_type: string; resource_id: string; before: Record<string, unknown> | null; after: Record<string, unknown> | null; created_at: string };

export const adminKeys = { all: (userId?: string) => ['admin', userId] as const };
function assertAdmin(userId?: string) {
  const user = authSession.getUser();
  if (!userId || user?.id !== userId || user.role !== 'admin') throw new Error('Administrator access is required.');
}
function useAdminQuery<T>(path: string) {
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({ queryKey: [...adminKeys.all(userId), path], enabled: Boolean(userId && user?.role === 'admin'), queryFn: async ({ signal }) => { assertAdmin(userId); const result = await api<T>(path, { signal }); assertAdmin(userId); return result; } });
}
export const useAdminAnalytics = () => useAdminQuery<Analytics>('/admin/analytics');
export const useAdminSettings = () => useAdminQuery<Setting[]>('/admin/settings');
export const useAdminExercises = (search = '') => useAdminQuery<Page<Exercise>>(`/admin/exercises?search=${encodeURIComponent(search)}&limit=100`);
export const useAdminFoods = (search = '') => useAdminQuery<Page<Food>>(`/admin/foods?search=${encodeURIComponent(search)}&limit=100`);
export const useAdminAnnouncements = () => useAdminQuery<Page<Announcement>>('/admin/announcements?include_expired=true&limit=100');
export const useAdminAudit = () => useAdminQuery<Page<Audit>>('/admin/audit?limit=50');
export const useAnnouncements = () => {
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({ queryKey: ['announcements', userId], enabled: Boolean(userId), queryFn: () => { if (!userId) throw new Error('Sign in required.'); return api<Page<Announcement>>('/announcements'); } });
};

export function useAdminMutation<T = unknown>() {
  const { user } = useAuth();
  const userId = user?.id;
  const client = useQueryClient();
  return useMutation({ mutationFn: async ({ path, method = 'POST', input }: { path: string; method?: 'POST' | 'PUT' | 'DELETE'; input?: unknown }) => { assertAdmin(userId); return api<T>(path, { method, json: input as Record<string, unknown> | undefined }); }, onSuccess: () => client.invalidateQueries({ queryKey: adminKeys.all(userId) }) });
}
