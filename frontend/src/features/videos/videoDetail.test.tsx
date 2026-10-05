import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { BASE, errorEnvelope, mockApi, videoDetail } from '../../test/api';
import { server } from '../../test/msw/server';
import { renderApp } from '../../test/renderApp';

describe('Video details page', () => {
  it('shows loading, then the video, its metrics and history', async () => {
    const api = mockApi();
    renderApp('/videos/vid-1');
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Shararat | Dhurandhar' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Saregama Music', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('101.9M')).toBeInTheDocument();
    expect(screen.getByText('0.61%')).toBeInTheDocument();
    expect(screen.getByText('Duration 3:49')).toBeInTheDocument();
    expect(screen.getByText(/Dashboard filters do not\s+apply/)).toBeInTheDocument();

    const history = await screen.findByRole('table', {
      name: 'Trending snapshots by date and country',
    });
    expect(within(history).getAllByRole('row')).toHaveLength(4); // header + 3 snapshots
    expect(
      screen.getByRole('img', { name: /view count at each trending snapshot/ }),
    ).toBeInTheDocument();
    expect(api.calls('/api/v1/videos/vid-1')).toHaveLength(1);
    expect(api.calls('/api/v1/videos/vid-1/history')).toHaveLength(1);
  });

  it('links to YouTube using the video ID, in a new tab', async () => {
    mockApi();
    renderApp('/videos/vid-1');
    const link = await screen.findByRole('link', { name: /Open on YouTube/ });
    expect(link).toHaveAttribute('href', 'https://www.youtube.com/watch?v=vid-1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders the description as text, never as HTML', async () => {
    mockApi();
    const { user } = renderApp('/videos/vid-1');
    await user.click(await screen.findByText('Show description'));
    expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByRole('list', { name: 'Tags' }).children).toHaveLength(3);
  });

  it('shows "Video not found" for a 404', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/videos/:videoId`, () =>
        errorEnvelope('not_found', 'Video not found.', 404),
      ),
    );
    renderApp('/videos/missing-id');
    expect(await screen.findByText('Video not found')).toBeInTheDocument();
    expect(screen.getByText(/No video with ID “missing-id”/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });

  it('shows a retryable error for server failures', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/videos/:videoId`, () =>
        errorEnvelope('internal_error', 'boom', 500),
      ),
    );
    renderApp('/videos/vid-1');
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByText('boom')).toBeNull();
  });

  it('shows an empty state when the history is empty', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/videos/:videoId`, () =>
        HttpResponse.json({ data: videoDetail('vid-2') }),
      ),
      http.get(`${BASE}/api/v1/videos/:videoId/history`, () => HttpResponse.json({ data: [] })),
    );
    renderApp('/videos/vid-2');
    expect(await screen.findByText('No trending history recorded')).toBeInTheDocument();
  });
});
