import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../../test/api';
import { renderApp } from '../../test/renderApp';
import { filterSearch, readFilters, writeFilters } from './urlFilters';

describe('URL filter helpers', () => {
  it('reads repeated country/category params with the backend parameter names', () => {
    const params = new URLSearchParams(
      'start_date=2025-12-01&end_date=2025-12-31&country=IN&country=US&category=News+%26+Politics&page=2',
    );
    expect(readFilters(params)).toEqual({
      start_date: '2025-12-01',
      end_date: '2025-12-31',
      country: ['IN', 'US'],
      category: ['News & Politics'],
    });
  });

  it('ignores empty values', () => {
    expect(readFilters(new URLSearchParams('country=&start_date=&category=%20'))).toEqual({});
  });

  it('writes filters while keeping unrelated params', () => {
    const next = writeFilters(new URLSearchParams('country=GB&sort=likes'), {
      country: ['IN', 'US'],
      start_date: '2025-12-01',
    });
    expect(next.getAll('country')).toEqual(['IN', 'US']);
    expect(next.get('start_date')).toBe('2025-12-01');
    expect(next.get('sort')).toBe('likes');
  });

  it('extracts only the filter part of a query string', () => {
    expect(
      filterSearch(new URLSearchParams('page=3&country=IN&tab=countries&end_date=2026-01-01')),
    ).toBe('?end_date=2026-01-01&country=IN');
    expect(filterSearch(new URLSearchParams('page=3'))).toBe('');
  });
});

describe('FilterBar', () => {
  it('shows backend options and the default window when no dates are set', async () => {
    mockApi();
    renderApp('/');
    const bar = await screen.findByRole('region', { name: 'Filters' });
    await waitFor(() => expect(within(bar).getByLabelText('From')).toHaveValue('2025-12-07'));
    expect(within(bar).getByLabelText('To')).toHaveValue('2026-01-05');
    expect(within(bar).getByLabelText('From')).toHaveAttribute('min', '2024-10-12');
    expect(within(bar).getByText(/Default window: latest 30 days/)).toBeInTheDocument();
  });

  it('selecting a country updates the URL, resets the page and refetches with the filter', async () => {
    const api = mockApi();
    const { user, location } = renderApp('/trending?page=3');
    await screen.findByText(/Showing 51–60 of 60 videos/);

    await user.click(screen.getByRole('button', { name: /Countries:/ }));
    await user.click(await screen.findByRole('checkbox', { name: /India/ }));

    await waitFor(() =>
      expect(new URLSearchParams(location().search).getAll('country')).toEqual(['IN']),
    );
    expect(new URLSearchParams(location().search).get('page')).toBeNull();
    await waitFor(() =>
      expect(
        api.calls('/api/v1/videos').some((u) => u.searchParams.getAll('country').includes('IN')),
      ).toBe(true),
    );
    const last = api.calls('/api/v1/videos').at(-1)!;
    expect(last.searchParams.get('page')).toBe('1');
  });

  it('changing the start date refetches the KPIs with that date', async () => {
    const api = mockApi();
    const { location } = renderApp('/');
    const from = await screen.findByLabelText('From');
    await waitFor(() => expect(from).not.toBeDisabled());
    // Date inputs receive a complete value at once (jsdom drops partial typed dates).
    fireEvent.change(from, { target: { value: '2025-12-20' } });
    await waitFor(() =>
      expect(new URLSearchParams(location().search).get('start_date')).toBe('2025-12-20'),
    );
    await waitFor(() =>
      expect(
        api
          .calls('/api/v1/overview/kpis')
          .some((u) => u.searchParams.get('start_date') === '2025-12-20'),
      ).toBe(true),
    );
  });

  it('reset clears every filter from the URL', async () => {
    mockApi();
    const { user, location } = renderApp('/?country=IN&category=Music&start_date=2025-12-20');
    await user.click(await screen.findByRole('button', { name: 'Reset filters' }));
    await waitFor(() => expect(location().search).toBe(''));
    expect(screen.queryByRole('button', { name: 'Reset filters' })).not.toBeInTheDocument();
  });

  it('shows the backend validation message when filters are rejected', async () => {
    mockApi();
    const { errorEnvelope, BASE } = await import('../../test/api');
    const { http } = await import('msw');
    const { server } = await import('../../test/msw/server');
    server.use(
      http.get(`${BASE}/api/v1/overview/kpis`, () =>
        errorEnvelope(
          'invalid_filter',
          'start_date: 2026-02-01 is outside the available range 2024-10-12 to 2026-01-05',
          422,
          'start_date',
        ),
      ),
    );
    renderApp('/?start_date=2026-02-01');
    expect(await screen.findByText("These filters can't be applied")).toBeInTheDocument();
    expect(
      screen.getByText(/outside the available range 2024-10-12 to 2026-01-05/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });
});
