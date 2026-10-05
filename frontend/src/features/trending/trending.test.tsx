import { screen, waitFor, within } from '@testing-library/react';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';

import { BASE, errorEnvelope, mockApi } from '../../test/api';
import { server } from '../../test/msw/server';
import { renderApp } from '../../test/renderApp';

const lastVideosRequest = (api: ReturnType<typeof mockApi>) =>
  api.calls('/api/v1/videos').at(-1)!.searchParams;

describe('Trending page', () => {
  it('renders one server page with the API defaults', async () => {
    const api = mockApi();
    renderApp('/trending');
    const table = await screen.findByRole('table', { name: 'Trending videos' });
    expect(within(table).getAllByRole('row')).toHaveLength(26);
    expect(screen.getByText('Showing 1–25 of 60 videos')).toBeInTheDocument();
    expect(Object.fromEntries(lastVideosRequest(api))).toEqual({
      sort: 'views',
      order: 'desc',
      page: '1',
      page_size: '25',
    });
  });

  it('paginates on the server and keeps the page in the URL', async () => {
    const api = mockApi();
    const { user, location } = renderApp('/trending');
    await screen.findByText('Showing 1–25 of 60 videos');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('Showing 26–50 of 60 videos');
    expect(new URLSearchParams(location().search).get('page')).toBe('2');
    expect(lastVideosRequest(api).get('page')).toBe('2');
    await user.click(screen.getByRole('button', { name: 'Last page' }));
    await screen.findByText('Showing 51–60 of 60 videos');
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('changing the page size requests the new size and returns to page 1', async () => {
    const api = mockApi();
    const { user, location } = renderApp('/trending?page=2');
    await screen.findByText('Showing 26–50 of 60 videos');
    await user.selectOptions(screen.getByLabelText('Rows per page'), '50');
    await screen.findByText('Showing 1–50 of 60 videos');
    expect(lastVideosRequest(api).get('page_size')).toBe('50');
    expect(new URLSearchParams(location().search).get('page')).toBeNull();
  });

  it('searches on the server and resets to the first page', async () => {
    const api = mockApi();
    const { user, location } = renderApp('/trending?page=2');
    await screen.findByText('Showing 26–50 of 60 videos');
    await user.type(screen.getByRole('searchbox'), 'number 1');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(lastVideosRequest(api).get('search')).toBe('number 1'));
    expect(lastVideosRequest(api).get('page')).toBe('1');
    expect(new URLSearchParams(location().search).get('search')).toBe('number 1');
    expect(await screen.findByText(/of 11 videos/)).toBeInTheDocument();
  });

  it('sorts via the API sort keys and order', async () => {
    const api = mockApi();
    const { user } = renderApp('/trending');
    await screen.findByText('Showing 1–25 of 60 videos');
    await user.selectOptions(screen.getByLabelText('Sort by'), 'engagement_rate');
    await waitFor(() => expect(lastVideosRequest(api).get('sort')).toBe('engagement_rate'));
    await user.click(screen.getByRole('button', { name: /switch to ascending/ }));
    await waitFor(() => expect(lastVideosRequest(api).get('order')).toBe('asc'));
  });

  it('shows a no-results state for a search with no matches', async () => {
    mockApi();
    const { user, location } = renderApp('/trending?search=zzz');
    expect(await screen.findByText('No videos match “zzz”')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear search' }));
    await waitFor(() => expect(new URLSearchParams(location().search).get('search')).toBeNull());
  });

  it('handles a page past the end of the results', async () => {
    mockApi();
    const { user } = renderApp('/trending?page=99');
    expect(await screen.findByText('This page is past the end of the results')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Go to the first page' }));
    expect(await screen.findByText('Showing 1–25 of 60 videos')).toBeInTheDocument();
  });

  it('shows the backend message for an invalid search', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/videos`, () =>
        errorEnvelope('invalid_parameter', 'search: must be 2 to 100 characters', 422, 'search'),
      ),
    );
    renderApp('/trending?search=a');
    expect(await screen.findByText('search: must be 2 to 100 characters')).toBeInTheDocument();
  });

  it('navigates to the video details page', async () => {
    mockApi();
    const { user, location } = renderApp('/trending?country=IN');
    await user.click(await screen.findByRole('link', { name: 'Video number 3' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Shararat | Dhurandhar' }),
    ).toBeInTheDocument();
    expect(location().pathname).toBe('/videos/vid-3');
    expect(location().search).toBe('?country=IN');
  });
});
