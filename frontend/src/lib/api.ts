import { z } from 'zod';

const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  role: z.enum(['user', 'admin']),
});
const sessionSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal('bearer'),
  user: userSchema,
});

export type AuthUser = z.infer<typeof userSchema>;
export type Credentials = { email: string; password: string };
type Session = z.infer<typeof sessionSchema>;
export type ApiOptions = Omit<RequestInit, 'body' | 'credentials'> & {
  json?: unknown;
  /** Public endpoints must not attach a bearer token or trigger a refresh. */
  auth?: boolean;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly fieldErrors: Readonly<Record<string, string>> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Credentials are never persisted. Only this module holds the in-memory bearer.
let session: Session | null = null;
let authEpoch = 0;
let refreshInFlight: Promise<AuthUser | null> | null = null;
let restoreInFlight: Promise<AuthUser | null> | null = null;
const listeners = new Set<() => void>();

function publishSession(next: Session | null) {
  session = next;
  listeners.forEach((listener) => listener());
}

async function responseError(response: Response): Promise<ApiError> {
  const fallback = response.status === 429
    ? 'Too many attempts. Please wait a minute and try again.'
    : response.status === 401
      ? 'Your session has expired. Please log in again.'
      : response.status === 403
        ? 'You do not have permission to perform this action.'
        : `The request failed (HTTP ${response.status}). Please try again.`;
  const data: unknown = await response.json().catch(() => null);
  if (typeof data !== 'object' || data === null) return new ApiError(fallback, response.status);
  const detail = 'detail' in data ? data.detail : 'message' in data ? data.message : null;
  if (typeof detail === 'string') return new ApiError(detail, response.status);
  const fields: Record<string, string> = {};
  const messages: string[] = [];
  if (Array.isArray(detail)) {
    for (const issue of detail) {
      if (typeof issue !== 'object' || issue === null || !('msg' in issue) || typeof issue.msg !== 'string') continue;
      const location: unknown = 'loc' in issue ? issue.loc : null;
      const field: unknown = Array.isArray(location) ? location.at(-1) : null;
      if (typeof field === 'string') fields[field] = issue.msg;
      messages.push(typeof field === 'string' ? `${field}: ${issue.msg}` : issue.msg);
    }
  }
  return new ApiError(messages.length ? messages.join(' ') : fallback, response.status, fields);
}

/** JSON API paths are relative to /api/v1, for example api('/auth/me'). */
export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('://')) {
    throw new Error('API paths must be relative to /api/v1.');
  }
  const { auth = true, json, ...request } = options;
  const epoch = authEpoch;
  const body = json === undefined ? undefined : JSON.stringify(json);
  let bearerUsed: string | undefined;

  async function send(): Promise<Response> {
    const headers = new Headers(request.headers);
    headers.set('Accept', 'application/json');
    if (json !== undefined) headers.set('Content-Type', 'application/json');
    bearerUsed = auth ? session?.access_token : undefined;
    if (bearerUsed) headers.set('Authorization', `Bearer ${bearerUsed}`);
    else headers.delete('Authorization');
    const deadline = AbortSignal.timeout(15_000);
    const signal = request.signal ? AbortSignal.any([request.signal, deadline]) : deadline;
    try {
      return await fetch(`/api/v1${path}`, { ...request, headers, body, signal, credentials: 'include' });
    } catch (error) {
      if (request.signal?.aborted) throw error;
      if (deadline.aborted) throw new ApiError('The server took too long to respond. Please try again.', 0);
      throw new ApiError('Could not reach the server. Check your connection and try again.', 0);
    }
  }

  let response = await send();
  if (response.status === 401 && auth && epoch === authEpoch) {
    // Another request may already have refreshed this token while ours was in flight.
    if (bearerUsed === session?.access_token) await refreshSession();
    if (session && epoch === authEpoch) {
      response = await send();
      // Retry only once. A rejected fresh token must not start a refresh loop.
      if (response.status === 401 && epoch === authEpoch && bearerUsed === session?.access_token) {
        publishSession(null);
      }
    }
  }
  if (!response.ok) throw await responseError(response);
  if (response.status === 204) return undefined as T;
  try {
    return await response.json() as T;
  } catch {
    throw new ApiError('The server returned an unreadable response. Please try again.', response.status);
  }
}

function parseSession(data: unknown): Session {
  const result = sessionSchema.safeParse(data);
  if (!result.success) throw new ApiError('The server returned an invalid session. Please try again.', 502);
  return result.data;
}

function refreshSession(): Promise<AuthUser | null> {
  if (refreshInFlight) return refreshInFlight;
  const epoch = authEpoch;
  refreshInFlight = (async () => {
    try {
      const next = parseSession(await api<unknown>('/auth/refresh', { method: 'POST', auth: false }));
      if (epoch === authEpoch) publishSession(next);
      return session?.user ?? null;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (epoch === authEpoch) publishSession(null);
        return session?.user ?? null;
      }
      throw error;
    }
  })().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

function restoreSession(): Promise<AuthUser | null> {
  if (restoreInFlight) return restoreInFlight;
  restoreInFlight = (async () => {
    const restoredUser = await refreshSession();
    if (!restoredUser) return null;
    const epoch = authEpoch;
    const result = userSchema.safeParse(await api<unknown>('/auth/me'));
    if (!result.success) throw new ApiError('The server returned an invalid account. Please try again.', 502);
    if (epoch === authEpoch && session) publishSession({ ...session, user: result.data });
    return session?.user ?? null;
  })().finally(() => { restoreInFlight = null; });
  return restoreInFlight;
}

async function authenticate(path: '/auth/login' | '/auth/register', credentials: Credentials): Promise<void> {
  const epoch = ++authEpoch;
  // Finish cookie rotation before replacing the cookie with a different session.
  await refreshInFlight?.catch(() => null);
  const next = parseSession(await api<unknown>(path, { method: 'POST', json: credentials, auth: false }));
  if (epoch === authEpoch) publishSession(next);
}

/** Session lifecycle for AuthProvider; consumers should use useAuth instead. */
export const authSession = {
  getUser: (): AuthUser | null => session?.user ?? null,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
  restore: restoreSession,
  login: (credentials: Credentials) => authenticate('/auth/login', credentials),
  register: (credentials: Credentials) => authenticate('/auth/register', credentials),
  async logout(): Promise<void> {
    const epoch = ++authEpoch;
    await refreshInFlight?.catch(() => null);
    await api<void>('/auth/logout', { method: 'POST', auth: false });
    if (epoch === authEpoch) publishSession(null);
  },
  async revokeAllSessions(): Promise<void> {
    const epoch = ++authEpoch;
    await refreshInFlight?.catch(() => null);
    await api<void>('/auth/revoke', { method: 'POST' });
    if (epoch === authEpoch) publishSession(null);
  },
};
