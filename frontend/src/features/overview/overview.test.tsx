import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { BASE, errorEnvelope, kpisResponse, mockApi } from '../../test/api';
import { server } from '../../test/msw/server';
import { renderApp } from '../../test/renderApp';

function kpiCard(label: string) {
  return screen.getByRole('heading', { level: 3, name: label }).closest('article')!;
}

describe('Overview page', () => {
  it('renders the API KPIs with the backend change semantics', async () => {
    mockApi();
    renderApp('/');
    await screen.findByText('53,668');
    expect(within(kpiCard('Trending volume')).getByText('-0.6%')).toBeInTheDocument();
    expect(within(kpiCard('Unique videos')).getByText('13,213')).toBeInTheDocument();
    expect(within(kpiCard('Views')).getByText('6.5B')).toBeInTheDocument();
    // Engagement change is in percentage points, not percent.
    expect(within(kpiCard('Engagement rate')).getByText('2.96%')).toBeInTheDocument();
    expect(within(kpiCard('Engagement rate')).getByText('+0.16 pp')).toBeInTheDocument();
    expect(within(kpiCard('Unique channels')).getByText('5,133')).toBeInTheDocument();
    expect(screen.getAllByText('vs previous 30 days').length).toBe(5);
    // Resolved period echoed by the backend.
    expect(screen.getByText(/Dec 7, 2025 – Jan 5, 2026 · 30 days/)).toBeInTheDocument();
  });

  it('explains when there is no earlier period to compare with', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/overview/kpis`, () => HttpResponse.json(kpisResponse(false))),
    );
    renderApp('/');
    await screen.findByText('53,668');
    expect(screen.getAllByText('No earlier period in the data')).toHaveLength(5);
  });

  it('renders the trend, category, country and top-video sections', async () => {
    mockApi();
    renderApp('/');
    expect(
      await screen.findByRole('img', { name: /daily trending volume and unique videos/ }),
    ).toBeInTheDocument();
    expect(await screen.findByRole('img', { name: /top categories by share/ })).toBeInTheDocument();
    expect(
      await screen.findByRole('img', { name: /trending volume by country/ }),
    ).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Top trending videos by views' });
    expect(within(table).getAllByRole('row')).toHaveLength(11); // header + 10 rows
    expect(within(table).getByRole('link', { name: 'Video number 1' })).toHaveAttribute(
      'href',
      '/videos/vid-1',
    );
  });

  it('requests each dashboard endpoint once, with the top-videos parameters', async () => {
    const api = mockApi();
    renderApp('/');
    await screen.findByRole('table', { name: 'Top trending videos by views' });
    await screen.findByText('53,668');
    for (const path of [
      '/api/v1/overview/kpis',
      '/api/v1/overview/daily-volume',
      '/api/v1/analytics/categories',
      '/api/v1/analytics/countries',
      '/api/v1/videos',
    ]) {
      expect(api.calls(path), path).toHaveLength(1);
    }
    const videos = api.calls('/api/v1/videos')[0]!;
    expect(Object.fromEntries(videos.searchParams)).toEqual({
      sort: 'views',
      order: 'desc',
      page: '1',
      page_size: '10',
    });
  });

  it('switching the trend to "By country" requests the country split', async () => {
    const api = mockApi();
    const { user } = renderApp('/');
    await user.click(await screen.findByRole('button', { name: 'By country' }));
    expect(await screen.findByRole('img', { name: /per country/ })).toBeInTheDocument();
    expect(api.calls('/api/v1/overview/daily-volume').at(-1)!.searchParams.get('split_by')).toBe(
      'country',
    );
  });

  it('shows an error with retry, and recovers', async () => {
    mockApi();
    let fail = true;
    server.use(
      http.get(`${BASE}/api/v1/overview/kpis`, () =>
        fail
          ? errorEnvelope('database_unavailable', 'down', 503)
          : HttpResponse.json(kpisResponse()),
      ),
    );
    const { user } = renderApp('/');
    expect(await screen.findByText('Data is temporarily unavailable')).toBeInTheDocument();
    expect(screen.getByText('Reference: req-test-1')).toBeInTheDocument();
    fail = false;
    await user.click(screen.getAllByRole('button', { name: 'Retry' })[0]!);
    expect(await screen.findByText('53,668')).toBeInTheDocument();
  });

  it('shows empty states when nothing matches', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/overview/kpis`, () => HttpResponse.json(kpisResponse(true, 0))),
      http.get(`${BASE}/api/v1/videos`, () =>
        HttpResponse.json({
          filters: kpisResponse().filters,
          data: { items: [], page: 1, page_size: 10, total: 0, total_pages: 0 },
        }),
      ),
    );
    renderApp('/?country=IN');
    await waitFor(() =>
      expect(screen.getAllByText('No trending videos in this selection')).toHaveLength(2),
    );
  });
});
