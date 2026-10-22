import type { Credentials, Message, Provider, Registration, User } from '../types';

function resolveOrigin(value: string): string {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) {
    throw new Error('VITE_API_ORIGIN must be an http(s) origin without a path.');
  }
  return url.origin;
}
export const API_ORIGIN = resolveOrigin(import.meta.env.VITE_API_ORIGIN || 'http://localhost:8000');

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object' || !('detail' in body)) return fallback;
  const detail = body.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first.msg === 'string') return first.msg;
  }
  return fallback;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body instanceof FormData) headers.delete('Content-Type');
  else if (init.body) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-Trace-Client', 'web');
  let response: Response;
  try {
    response = await fetch(API_ORIGIN + '/api/v1' + path, {
      ...init, method, headers, credentials: 'include', cache: 'no-store',
    });
  } catch {
    throw new ApiError(0, 'Could not connect to Trace. Check your connection and try again.');
  }
  const body: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) {
    const seconds = Number(response.headers.get('Retry-After'));
    throw new ApiError(
      response.status,
      errorDetail(body, 'Something went wrong. Please try again.'),
      Number.isFinite(seconds) && seconds > 0 ? seconds : undefined,
    );
  }
  return body as T;
}

function post<T>(path: string, body?: unknown) {
  return request<T>(path, { method: 'POST', ...(body === undefined ? {} : {body: JSON.stringify(body)}) });
}
export const api = {
  me: () => request<User>('/auth/me'),
  login: (body: Credentials) => post<User>('/auth/login', body),
  register: (body: Registration) => post<User>('/auth/register', body),
  logout: () => post<void>('/auth/logout'),
  resendVerification: (email: string) => post<Message>('/auth/email/verification-request', { email }),
  forgotPassword: (email: string) => post<Message>('/auth/password/forgot', { email }),
};

export function providerLoginUrl(provider: Provider) {
  return API_ORIGIN + '/api/v1/auth/oauth/' + provider + '/login';
}
export function readableError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong. Please try again.';
  if (error.status === 429) {
    return error.retryAfter
      ? 'Too many attempts. Try again in about ' + Math.ceil(error.retryAfter / 60) + ' minute(s).'
      : 'Too many attempts. Please try again later.';
  }
  return error.message;
}

const oauthErrors: Record<string, string> = {
  provider_unavailable: 'This sign-in provider is unavailable. Try email sign-in or come back later.',
  unsupported_provider: 'This sign-in provider is not supported.',
  oauth_cancelled: 'Sign-in was cancelled. You can try again when you are ready.',
  oauth_invalid: 'This sign-in attempt expired or could not be verified. Please start again.',
  provider_error: 'We could not complete provider sign-in. Please try again.',
  account_exists: 'An account already uses this email. Sign in with the method you used before. Provider linking is not available yet.',
  account_unavailable: 'This account is unavailable. Please use another sign-in method.',
};
export function oauthErrorMessage(code: string | null): string {
  if (!code) return '';
  return Object.prototype.hasOwnProperty.call(oauthErrors, code)
    ? oauthErrors[code] : 'Sign-in could not be completed. Please try again.';
}
