import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../../test/api';
import { renderApp } from '../../test/renderApp';

describe('Analytics page', () => {
  it('opens on Categories and only requests that section', async () => {
    const api = mockApi();
    renderApp('/analytics');
    const table = await screen.findByRole('table', { name: 'Category performance' });
    expect(within(table).getByText('Gaming')).toBeInTheDocument();
    expect(within(table).getByText('53.8%')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Categories' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await screen.findByRole('img', { name: /top categories/ });
    expect(api.calls('/api/v1/overview/daily-volume').at(-1)!.searchParams.get('split_by')).toBe(
      'category',
    );
    expect(api.calls('/api/v1/analytics/countries')).toHaveLength(0);
    expect(api.calls('/api/v1/analytics/engagement')).toHaveLength(0);
    expect(api.calls('/api/v1/analytics/channels')).toHaveLength(0);
  });

  it('switches tabs through the URL and explains country views', async () => {
    const api = mockApi();
    const { user, location } = renderApp('/analytics?country=IN');
    await screen.findByRole('table', { name: 'Category performance' });
    await user.click(screen.getByRole('tab', { name: 'Countries' }));
    const table = await screen.findByRole('table', { name: 'Country performance' });
    expect(within(table).getByText('India')).toBeInTheDocument();
    expect(screen.getByText(/not views\s+from that country/)).toBeInTheDocument();
    const params = new URLSearchParams(location().search);
    expect(params.get('tab')).toBe('countries');
    expect(params.getAll('country')).toEqual(['IN']);
    expect(api.calls('/api/v1/analytics/countries').at(-1)!.searchParams.getAll('country')).toEqual(
      ['IN'],
    );
  });

  it('renders engagement totals, percentiles, histogram and scatter', async () => {
    const api = mockApi();
    renderApp('/analytics?tab=engagement');
    expect(await screen.findByText('Without views (excluded)')).toBeInTheDocument();
    expect(screen.getByText('29')).toBeInTheDocument();
    expect(screen.getByText(/median 3\.06%/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Histogram/ })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Scatter plot/ })).toBeInTheDocument();
    expect(
      screen.getByRole('table', { name: 'Engagement percentiles by category' }),
    ).toBeInTheDocument();
    expect(
      api.calls('/api/v1/analytics/engagement').at(-1)!.searchParams.get('scatter_limit'),
    ).toBe('200');
  });

  it('ranks channels by the selected API sort key', async () => {
    const api = mockApi();
    const { user } = renderApp('/analytics?tab=channels');
    const table = await screen.findByRole('table', { name: 'Top channels' });
    expect(within(table).getByText('KAYE')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Rank by'), 'views');
    await waitFor(() =>
      expect(api.calls('/api/v1/analytics/channels').at(-1)!.searchParams.get('sort')).toBe(
        'views',
      ),
    );
    await user.selectOptions(screen.getByLabelText('Show'), '25');
    await waitFor(() =>
      expect(api.calls('/api/v1/analytics/channels').at(-1)!.searchParams.get('limit')).toBe('25'),
    );
  });

  it('falls back to Categories for an unknown tab', async () => {
    mockApi();
    renderApp('/analytics?tab=lifecycle');
    expect(await screen.findByRole('table', { name: 'Category performance' })).toBeInTheDocument();
  });
});
