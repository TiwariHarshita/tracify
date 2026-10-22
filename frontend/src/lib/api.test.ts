import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, oauthErrorMessage, providerLoginUrl, readableError, request } from './api';

afterEach(() => vi.unstubAllGlobals());
describe('HTTP client', () => {
  it('includes cookies and the protected-write header', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({id:'user'}), {status:200}));
    vi.stubGlobal('fetch', fetch);
    await api.login({ email:'member@example.com', password:'private-password' });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/v1/auth/login');
    expect(options.credentials).toBe('include');
    expect(options.headers.get('X-Trace-Client')).toBe('web');
    expect(options.headers.get('Content-Type')).toBe('application/json');
  });
  it('accepts a bodyless 204 logout', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, {status:204})));
    await expect(api.logout()).resolves.toBeUndefined();
  });
  it('preserves Retry-After without exposing the request body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Too many attempts'}), {status:429, headers:{'Retry-After':'900'}})));
    await expect(api.login({email:'member@example.com', password:'secret'})).rejects.toMatchObject({status:429, retryAfter:900});
    expect(readableError(new ApiError(429, 'Limited', 900))).toContain('15 minute');
  });
  it('does not include validation input values in the error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:[{msg:'Password is too short', input:'secret-value'}]}), {status:422})));
    await expect(api.login({email:'member@example.com',password:'x'})).rejects.toThrow('Password is too short');
  });
  it('makes provider buttons use full-page backend URLs', () => {
    expect(providerLoginUrl('github')).toBe('http://localhost:8000/api/v1/auth/oauth/github/login');
    expect(providerLoginUrl('google')).toBe('http://localhost:8000/api/v1/auth/oauth/google/login');
  });
  it('maps only recognized OAuth error codes to frontend copy', () => {
    expect(oauthErrorMessage('account_exists')).toContain('method you used before');
    expect(oauthErrorMessage('<script>bad</script>')).not.toContain('<script>');
  });
});

it('lets the browser set the multipart boundary while keeping cookies and write protection',async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({id:'dataset'}),{status:200}));
  vi.stubGlobal('fetch',fetch);
  const body=new FormData();body.append('file',new File(['a\n1\n'],'public.csv',{type:'text/csv'}));
  await request('/datasets/upload',{method:'POST',body});
  const options=fetch.mock.calls[0][1];
  expect(options.headers.has('Content-Type')).toBe(false);
  expect(options.headers.get('X-Trace-Client')).toBe('web');
  expect(options.credentials).toBe('include');
});
