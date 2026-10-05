import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import type { Member, Role } from '../../api/types';
import { BASE, currentUser, errorEnvelope, member, mockApi, USER_IDS } from '../../test/api';
import { server } from '../../test/msw/server';
import { renderApp } from '../../test/renderApp';

const MEMBERS_URL = `${BASE}/api/v1/tenant/members`;

function mockTeam(role: Role, members?: Member[]) {
  mockApi({ user: currentUser(role) });
  const list = members ?? [
    member(USER_IDS.self, role, { display_name: 'Pat Example', email: 'pat@example.com' }),
    member(USER_IDS.owner, 'OWNER'),
    member(USER_IDS.member, 'MEMBER', { last_login_at: null }),
  ];
  const patches: { id: string; body: unknown }[] = [];
  const posts: unknown[] = [];
  server.use(
    http.get(MEMBERS_URL, () => HttpResponse.json({ data: list })),
    http.patch(`${MEMBERS_URL}/:id`, async ({ request, params }) => {
      patches.push({ id: String(params.id), body: await request.json() });
      return HttpResponse.json({ data: list.find((m) => m.id === params.id) });
    }),
    http.post(MEMBERS_URL, async ({ request }) => {
      const body = (await request.json()) as { email: string; display_name: string; role: Role };
      posts.push(body);
      return HttpResponse.json({ data: member('new-id', body.role, body) }, { status: 201 });
    }),
  );
  return { patches, posts };
}

const row = (name: RegExp) => screen.getByRole('row', { name });

describe('Team page', () => {
  it('lists the workspace members for an admin, with only the allowed controls', async () => {
    mockTeam('ADMIN');
    renderApp('/team');
    expect(await screen.findByRole('heading', { level: 1, name: 'Team' })).toBeInTheDocument();
    expect(screen.getByText(/People in Acme Analytics/)).toBeInTheDocument();
    await screen.findByText('owner@example.com');

    // Own row: no controls (nobody changes their own membership).
    expect(within(row(/Pat Example/)).queryByRole('combobox')).not.toBeInTheDocument();
    expect(within(row(/Pat Example/)).getByText('(you)')).toBeInTheDocument();
    // An admin cannot change owners.
    expect(within(row(/Owner Person/)).queryByRole('combobox')).not.toBeInTheDocument();
    expect(within(row(/Owner Person/)).queryByRole('button')).not.toBeInTheDocument();
    // ...but can manage members, and cannot grant OWNER.
    const roleSelect = within(row(/Member Person/)).getByRole('combobox', {
      name: 'Role for Member Person',
    });
    expect(
      within(roleSelect)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Admin', 'Member']);
    expect(within(row(/Member Person/)).getByText('Never')).toBeInTheDocument();
  });

  it('changes a role and deactivates a member through the API', async () => {
    const { patches } = mockTeam('OWNER');
    const { user } = renderApp('/team');
    await screen.findByText('member@example.com');
    await user.selectOptions(
      within(row(/Member Person/)).getByRole('combobox', { name: 'Role for Member Person' }),
      'ADMIN',
    );
    await waitFor(() => expect(patches).toHaveLength(1));
    await user.click(
      within(row(/Member Person/)).getByRole('button', { name: 'Deactivate Member Person' }),
    );
    await waitFor(() => expect(patches).toHaveLength(2));
    expect(patches).toEqual([
      { id: USER_IDS.member, body: { role: 'ADMIN' } },
      { id: USER_IDS.member, body: { is_active: false } },
    ]);
  });

  it('owners can grant every role', async () => {
    mockTeam('OWNER');
    renderApp('/team');
    await screen.findByText('member@example.com');
    const roles = within(screen.getByLabelText('Role')).getAllByRole('option');
    expect(roles.map((o) => o.textContent)).toEqual(['Owner', 'Admin', 'Member']);
  });

  it('adds a member (the request never carries a tenant id)', async () => {
    const { posts } = mockTeam('ADMIN');
    const { user } = renderApp('/team');
    await screen.findByText('member@example.com');
    const form = screen.getByRole('form', { name: 'Add a member' });
    await user.type(within(form).getByLabelText('Name'), 'Sam New');
    await user.type(within(form).getByLabelText('Email'), 'sam@example.com');
    await user.type(within(form).getByLabelText('Initial password'), 'initial passphrase');
    await user.selectOptions(within(form).getByLabelText('Role'), 'ADMIN');
    await user.click(within(form).getByRole('button', { name: 'Add member' }));
    expect(await screen.findByText('sam@example.com was added as Admin.')).toBeInTheDocument();
    expect(posts).toEqual([
      {
        display_name: 'Sam New',
        email: 'sam@example.com',
        password: 'initial passphrase',
        role: 'ADMIN',
      },
    ]);
  });

  it('shows the server decision when it refuses a change', async () => {
    mockTeam('ADMIN');
    server.use(
      http.patch(`${MEMBERS_URL}/:id`, () =>
        errorEnvelope('forbidden', 'Your role cannot change OWNER members.', 403),
      ),
    );
    const { user } = renderApp('/team');
    await screen.findByText('member@example.com');
    await user.click(
      within(row(/Member Person/)).getByRole('button', { name: 'Deactivate Member Person' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your role cannot change OWNER members.',
    );
  });
});
