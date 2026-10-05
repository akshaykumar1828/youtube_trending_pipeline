import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { renderApp } from '../test/renderApp';

describe('routing', () => {
  beforeEach(() => {
    mockApi();
  });

  it.each([
    ['/', 'Overview'],
    ['/trending', 'Trending videos'],
    ['/analytics', 'Analytics'],
  ])('renders %s', async (path, heading) => {
    renderApp(path);
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });

  it('renders the video details route', async () => {
    renderApp('/videos/vid-1');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Shararat | Dhurandhar' }),
    ).toBeInTheDocument();
  });

  it('shows a not-found page for unknown routes, inside the app shell', async () => {
    renderApp('/does-not-exist');
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
    expect(screen.getAllByRole('navigation', { name: 'Main' }).length).toBeGreaterThan(0);
  });

  it('marks the active navigation item', async () => {
    renderApp('/analytics');
    await screen.findByRole('heading', { level: 1, name: 'Analytics' });
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    expect(within(nav).getByRole('link', { name: 'Analytics' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
  });

  it('keeps global filters (but not page-specific params) when navigating', async () => {
    const { user, location } = renderApp(
      '/trending?country=IN&start_date=2025-12-10&page=3&sort=likes',
    );
    await screen.findByRole('heading', { level: 1, name: 'Trending videos' });
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    await user.click(within(nav).getByRole('link', { name: 'Analytics' }));
    await screen.findByRole('heading', { level: 1, name: 'Analytics' });
    const params = new URLSearchParams(location().search);
    expect(location().pathname).toBe('/analytics');
    expect(params.getAll('country')).toEqual(['IN']);
    expect(params.get('start_date')).toBe('2025-12-10');
    expect(params.get('page')).toBeNull();
    expect(params.get('sort')).toBeNull();
  });

  it('opens and closes the mobile navigation drawer', async () => {
    const { user, location } = renderApp('/');
    await screen.findByRole('heading', { level: 1, name: 'Overview' });
    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    const drawer = await screen.findByRole('dialog', { name: 'Navigation' });
    await user.click(within(drawer).getByRole('link', { name: 'Trending' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(location().pathname).toBe('/trending');
  });
});
