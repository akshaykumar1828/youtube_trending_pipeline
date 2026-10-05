import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import type { CurrentUser } from '../../api/types';
import { BASE, currentUser, errorEnvelope, mockApi, notAuthenticated } from '../../test/api';
import { server } from '../../test/msw/server';
import { renderApp } from '../../test/renderApp';
import { safeNextPath } from './permissions';

const LOGIN_URL = `${BASE}/api/v1/auth/login`;
const REGISTER_URL = `${BASE}/api/v1/auth/register`;
const LOGOUT_URL = `${BASE}/api/v1/auth/logout`;
const ME_URL = `${BASE}/api/v1/auth/me`;

/** Records POST bodies and the request's credentials mode. */
function capturePost(url: string, respond: () => Response) {
  const calls: { body: unknown; credentials: RequestCredentials }[] = [];
  server.use(
    http.post(url, async ({ request }) => {
      calls.push({
        body: await request.json().catch(() => null),
        credentials: request.credentials,
      });
      return respond();
    }),
  );
  return calls;
}

/** After a successful sign-in, /auth/me reports the new user. */
function signInSucceeds(user: CurrentUser = currentUser()) {
  return capturePost(LOGIN_URL, () => {
    server.use(http.get(ME_URL, () => HttpResponse.json({ data: user })));
    return HttpResponse.json({ data: user });
  });
}

describe('protected routes', () => {
  it('redirects a signed-out visitor to sign-in, keeping the destination, without loading data', async () => {
    const api = mockApi({ user: null });
    const { location } = renderApp('/analytics?country=IN');
    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(location().pathname).toBe('/login');
    expect(new URLSearchParams(location().search).get('next')).toBe('/analytics?country=IN');
    expect(api.requests).toHaveLength(0); // no analytics request was even attempted
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();
  });

  it('shows an error with retry (not a redirect) when the session check itself fails', async () => {
    mockApi();
    server.use(http.get(ME_URL, () => HttpResponse.error()));
    const { location } = renderApp('/');
    expect(await screen.findByText("Can't reach the API")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(location().pathname).toBe('/');
  });

  it('sends a user whose session expires mid-visit back to sign-in', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/overview/kpis`, () => {
        server.use(http.get(ME_URL, () => notAuthenticated()));
        return notAuthenticated();
      }),
    );
    const { location } = renderApp('/');
    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(location().pathname).toBe('/login');
  });
});

describe('sign in', () => {
  it('signs in with the session cookie and continues to the requested page', async () => {
    mockApi({ user: null });
    const calls = signInSucceeds();
    const { user, location } = renderApp('/login?next=%2Fanalytics');
    await user.type(await screen.findByLabelText('Email'), 'pat@example.com');
    await user.type(screen.getByLabelText('Password'), 'correct horse battery');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument();
    expect(location().pathname).toBe('/analytics');
    expect(calls).toEqual([
      {
        body: { email: 'pat@example.com', password: 'correct horse battery' },
        credentials: 'include',
      },
    ]);
  });

  it('shows the generic error for wrong credentials and stays on the page', async () => {
    mockApi({ user: null });
    capturePost(LOGIN_URL, () =>
      errorEnvelope('invalid_credentials', 'Invalid email or password.', 401),
    );
    const { user, location } = renderApp('/login');
    await user.type(await screen.findByLabelText('Email'), 'pat@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrong password!');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.');
    expect(location().pathname).toBe('/login');
  });

  it('explains a temporary lockout', async () => {
    mockApi({ user: null });
    capturePost(LOGIN_URL, () =>
      errorEnvelope('too_many_attempts', 'Too many failed sign-in attempts. Try again later.', 429),
    );
    const { user } = renderApp('/login');
    await user.type(await screen.findByLabelText('Email'), 'pat@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrong password!');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many failed sign-in attempts');
  });

  it('sends an already signed-in user straight on', async () => {
    mockApi();
    const { location } = renderApp('/login');
    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(location().pathname).toBe('/');
  });

  it.each([
    ['/analytics?country=IN', '/analytics?country=IN'],
    [null, '/'],
    ['https://evil.example', '/'],
    ['//evil.example/path', '/'],
    ['/\\evil.example', '/'],
    ['/login', '/'],
    ['/register?next=/x', '/'],
  ])('only follows same-app next paths: %s -> %s', (next, expected) => {
    expect(safeNextPath(next)).toBe(expected);
  });
});

describe('registration', () => {
  it('checks the password length before sending anything', async () => {
    mockApi({ user: null });
    const calls = capturePost(REGISTER_URL, () => HttpResponse.json({}));
    const { user } = renderApp('/register');
    await user.type(await screen.findByLabelText('Your name'), 'Pat');
    await user.type(screen.getByLabelText('Email'), 'pat@example.com');
    await user.type(screen.getByLabelText('Password'), 'short');
    await user.click(screen.getByRole('button', { name: 'Create workspace' }));
    expect(await screen.findByText('Password must be at least 12 characters.')).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('creates the workspace, signs in as its owner and opens the overview', async () => {
    mockApi({ user: null });
    const owner = currentUser('OWNER');
    const calls = capturePost(REGISTER_URL, () => {
      server.use(http.get(ME_URL, () => HttpResponse.json({ data: owner })));
      return HttpResponse.json({ data: owner }, { status: 201 });
    });
    const { user, location } = renderApp('/register');
    await user.type(await screen.findByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), 'pat@example.com');
    await user.type(screen.getByLabelText('Password'), 'a long passphrase');
    await user.click(screen.getByRole('button', { name: 'Create workspace' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(location().pathname).toBe('/');
    expect(calls[0]).toEqual({
      body: {
        display_name: 'Pat Example',
        email: 'pat@example.com',
        password: 'a long passphrase',
        tenant_name: null,
      },
      credentials: 'include',
    });
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    expect(within(nav).getByRole('link', { name: 'Team' })).toBeInTheDocument();
  });

  it('shows a taken email next to the email field', async () => {
    mockApi({ user: null });
    capturePost(REGISTER_URL, () =>
      errorEnvelope('email_taken', 'An account with this email already exists.', 409, 'email'),
    );
    const { user } = renderApp('/register');
    await user.type(await screen.findByLabelText('Your name'), 'Pat');
    await user.type(screen.getByLabelText('Email'), 'pat@example.com');
    await user.type(screen.getByLabelText('Password'), 'a long passphrase');
    await user.click(screen.getByRole('button', { name: 'Create workspace' }));
    const email = screen.getByLabelText('Email');
    await waitFor(() => expect(email).toHaveAttribute('aria-invalid', 'true'));
    expect(email).toHaveAccessibleDescription('An account with this email already exists.');
  });
});

describe('signed-in user and sign out', () => {
  it('shows who is signed in, their role and workspace, and signs out', async () => {
    mockApi({ user: currentUser('ADMIN') });
    const calls = capturePost(LOGOUT_URL, () => {
      server.use(http.get(ME_URL, () => notAuthenticated()));
      return HttpResponse.json({ data: { status: 'logged_out' } });
    });
    const { user, location } = renderApp('/analytics');
    await screen.findByRole('heading', { level: 1, name: 'Analytics' });
    await user.click(screen.getByRole('button', { name: 'Account: Pat Example' }));
    const menu = await screen.findByRole('dialog');
    expect(within(menu).getByText('pat@example.com')).toBeInTheDocument();
    expect(within(menu).getByText('Admin')).toBeInTheDocument();
    expect(within(menu).getByText('Acme Analytics')).toBeInTheDocument();
    await user.click(within(menu).getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(location().pathname).toBe('/login');
    expect(location().search).toBe('');
    expect(calls).toHaveLength(1);
    expect(calls[0]!.credentials).toBe('include');
  });

  it('shows the API forbidden response as an access-denied state', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/analytics/categories`, () =>
        errorEnvelope('forbidden', 'You do not have permission to perform this action.', 403),
      ),
    );
    renderApp('/analytics');
    expect((await screen.findAllByText('Access denied')).length).toBeGreaterThan(0);
  });
});

describe('role-aware navigation', () => {
  it.each([
    ['MEMBER', false],
    ['ADMIN', true],
    ['OWNER', true],
  ] as const)('%s sees Team in the navigation: %s', async (role, visible) => {
    mockApi({ user: currentUser(role) });
    renderApp('/');
    await screen.findByRole('heading', { level: 1, name: 'Overview' });
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    for (const label of ['Overview', 'Trending', 'Analytics', 'Predictions']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(within(nav).queryByRole('link', { name: 'Team' }) !== null).toBe(visible);
  });

  it('shows access denied to a member who opens /team directly, without requesting members', async () => {
    mockApi({ user: currentUser('MEMBER') });
    const memberRequests: string[] = [];
    server.use(
      http.get(`${BASE}/api/v1/tenant/members`, ({ request }) => {
        memberRequests.push(request.url);
        return HttpResponse.json({ data: [] });
      }),
    );
    renderApp('/team');
    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(screen.getByText(/Your role \(Member\) does not include access/)).toBeInTheDocument();
    expect(memberRequests).toHaveLength(0);
  });
});
