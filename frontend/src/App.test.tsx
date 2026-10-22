import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './auth/AuthContext';
import { api, ApiError } from './lib/api';
import { workspaceApi } from './lib/workspace';
import type { User } from './types';

const member: User = {id:'c4ba5f4d-f224-4071-b8c0-b88491989f4c',name:'Ava',email:'ava@example.com',email_verified:true};
function mount(path='/login') {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>);
}
async function fillLogin() {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Email address'), 'ava@example.com');
  await user.type(screen.getByLabelText('Password', {exact:true}), 'password-for-tests');
  await user.click(screen.getByRole('button', {name:/^Sign in/}));
  return user;
}
beforeEach(() => {
  vi.spyOn(workspaceApi,'datasets').mockResolvedValue([]);
  vi.spyOn(workspaceApi,'reports').mockResolvedValue([]);
  vi.spyOn(api,'me').mockRejectedValue(new ApiError(401,'Not signed in'));
  vi.spyOn(api,'login').mockResolvedValue(member);
  vi.spyOn(api,'logout').mockResolvedValue(undefined);
  vi.spyOn(api,'register').mockResolvedValue({...member,email_verified:false});
  vi.spyOn(api,'forgotPassword').mockResolvedValue({message:'If this account has a password, a reset email will be sent.'});
  vi.spyOn(api,'resendVerification').mockResolvedValue({message:'If this account needs verification, an email will be sent.'});
});
describe('authenticated navigation', () => {
  it('checks the session before rendering a private page', async () => {
    let resolve!: (user: User) => void;
    vi.mocked(api.me).mockImplementation(() => new Promise(done => {resolve=done;}));
    mount('/app');
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session');
    expect(screen.queryByText('Your next insight starts here.')).not.toBeInTheDocument();
    await act(async () => { resolve(member); });
    expect(await screen.findByRole('heading', {name:'Welcome, Ava.'})).toBeInTheDocument();
  });
  it('redirects a signed-out private URL to login', async () => {
    mount('/app/account');
    expect(await screen.findByRole('heading',{name:'Sign in to Trace'})).toBeInTheDocument();
  });
  it('signs in and renders the actual current user', async () => {
    mount(); await fillLogin();
    expect(await screen.findByRole('heading',{name:'Welcome, Ava.'})).toBeInTheDocument();
    expect(api.login).toHaveBeenCalledWith({email:'ava@example.com',password:'password-for-tests'});
  });
  it('restores an account page from /me on a fresh load', async () => {
    vi.mocked(api.me).mockResolvedValue(member);
    mount('/app/account');
    expect(await screen.findByRole('heading',{name:'A little about you.'})).toBeInTheDocument();
    expect(screen.getByText('ava@example.com')).toBeInTheDocument();
  });
  it('does not treat a backend outage as a signed-out session', async () => {
    vi.mocked(api.me).mockRejectedValue(new ApiError(0,'Offline'));
    mount('/app');
    expect(await screen.findByRole('heading',{name:'We could not check your session.'})).toBeInTheDocument();
    vi.mocked(api.me).mockResolvedValue(member);
    await userEvent.click(screen.getByRole('button',{name:'Try again'}));
    expect(await screen.findByRole('heading',{name:'Welcome, Ava.'})).toBeInTheDocument();
  });
  it('keeps an invalid login on the login page', async () => {
    vi.mocked(api.login).mockRejectedValue(new ApiError(401,'Invalid email or password'));
    mount(); await fillLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
    expect(screen.getByRole('heading',{name:'Sign in to Trace'})).toBeInTheDocument();
  });
  it('offers verification resend after an unverified password login', async () => {
    vi.mocked(api.login).mockRejectedValue(new ApiError(403,'Verify your email before signing in'));
    mount(); const user=await fillLogin();
    await user.click(await screen.findByRole('link',{name:'Resend verification email'}));
    expect(await screen.findByRole('heading',{name:'Check your email'})).toBeInTheDocument();
    expect(screen.getByLabelText('Email address')).toHaveValue('ava@example.com');
  });
  it('shows bounded provider collision errors', async () => {
    mount('/login?auth_error=account_exists&provider=github');
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign in with the method you used before');
  });
  it('shows rate limit wait information', async () => {
    vi.mocked(api.login).mockRejectedValue(new ApiError(429,'Limited',900));
    mount(); await fillLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent('15 minute');
  });
  it('logs out only after server-side logout succeeds', async () => {
    vi.mocked(api.me).mockResolvedValue(member);
    mount('/app');
    await screen.findByRole('heading',{name:'Welcome, Ava.'});
    await userEvent.click(screen.getByRole('button',{name:/Ava/}));
    await userEvent.click(screen.getByRole('button',{name:'Sign out'}));
    expect(await screen.findByRole('heading',{name:'Sign in to Trace'})).toBeInTheDocument();
    expect(api.logout).toHaveBeenCalledTimes(1);
  });
  it('preserves signed-in state and shows errors if logout fails', async () => {
    vi.mocked(api.me).mockResolvedValue(member);
    vi.mocked(api.logout).mockRejectedValue(new ApiError(0,'Could not connect'));
    mount('/app');
    await screen.findByRole('heading',{name:'Welcome, Ava.'});
    await userEvent.click(screen.getByRole('button',{name:/Ava/}));
    await userEvent.click(screen.getByRole('button',{name:'Sign out'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not connect');
    expect(screen.getByRole('heading',{name:'Welcome, Ava.'})).toBeInTheDocument();
  });
});
describe('registration and recovery', () => {
  it('registers and waits for email verification without logging in', async () => {
    mount('/register');
    const user=userEvent.setup();
    await user.type(await screen.findByLabelText('Your name'),'Ava');
    await user.type(screen.getByLabelText('Email address'),'ava@example.com');
    await user.type(screen.getByLabelText('Password',{exact:true}),'password-for-tests');
    await user.type(screen.getByLabelText('Confirm password'),'password-for-tests');
    await user.click(screen.getByRole('button',{name:/^Create account/}));
    expect(await screen.findByRole('heading',{name:'Check your email'})).toBeInTheDocument();
    expect(api.login).not.toHaveBeenCalled();
  });
  it('rejects mismatched confirmation before calling the API', async () => {
    mount('/register');
    const user=userEvent.setup();
    await user.type(await screen.findByLabelText('Your name'),'Ava');
    await user.type(screen.getByLabelText('Email address'),'ava@example.com');
    await user.type(screen.getByLabelText('Password',{exact:true}),'password-for-tests');
    await user.type(screen.getByLabelText('Confirm password'),'different-password');
    await user.click(screen.getByRole('button',{name:/^Create account/}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Passwords do not match');
    expect(api.register).not.toHaveBeenCalled();
  });
  it('shows generic password recovery copy from the API', async () => {
    mount('/forgot-password');
    await userEvent.type(await screen.findByLabelText('Email address'),'unknown@example.com');
    await userEvent.click(screen.getByRole('button',{name:'Send reset link'}));
    expect(await screen.findByRole('status')).toHaveTextContent('If this account has a password');
  });
  it('resends verification through the existing endpoint', async () => {
    mount('/check-email');
    await userEvent.type(await screen.findByLabelText('Email address'),'ava@example.com');
    await userEvent.click(screen.getByRole('button',{name:'Resend verification link'}));
    await waitFor(() => expect(api.resendVerification).toHaveBeenCalledWith('ava@example.com'));
    expect(await screen.findByRole('status')).toHaveTextContent('If this account needs verification');
  });
});
