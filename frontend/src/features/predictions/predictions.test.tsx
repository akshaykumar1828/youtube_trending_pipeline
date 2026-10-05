import { screen, waitFor, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { BASE, errorEnvelope, mockApi, predictionResponse } from '../../test/api';
import { server } from '../../test/msw/server';
import { renderApp } from '../../test/renderApp';

const PREDICT_URL = `${BASE}/api/v1/predictions`;

async function fillValidForm(user: UserEvent) {
  await user.type(await screen.findByLabelText(/^Title/), 'Last over thriller | Highlights!');
  await user.type(screen.getByLabelText(/^Tags/), 'cricket, highlights ,');
  await user.type(screen.getByLabelText(/^Duration/), '140');
  await user.type(screen.getByLabelText(/^Channel name/), 'Star Sports');
  await user.type(screen.getByLabelText(/^Subscribers/), '8800000');
  await user.type(screen.getByLabelText(/^Videos on channel/), '14200');
  await user.type(screen.getByLabelText(/^Total channel views/), '19600000000');
  await user.selectOptions(screen.getByLabelText(/^Category/), 'Sports');
  await user.selectOptions(screen.getByLabelText(/^Country/), 'IN');
}

const submit = (user: UserEvent) => user.click(screen.getByRole('button', { name: 'Score video' }));

describe('Predictions page', () => {
  it('is routed, in the navigation, and shows the disclaimer', async () => {
    mockApi();
    renderApp('/predictions');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'ML predictions' }),
    ).toBeInTheDocument();
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    expect(within(nav).getByRole('link', { name: 'Predictions' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      screen.getByText(
        'This model estimates high-performance probability for videos that are already represented in the trending dataset. It does not predict whether an arbitrary video will enter YouTube Trending.',
      ),
    ).toBeInTheDocument();
  });

  it('loads model info and does not run a prediction on page load', async () => {
    const api = mockApi();
    renderApp('/predictions');
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(await screen.findByText(/A video is labelled high-performing/)).toBeInTheDocument();
    expect(screen.getByText('Singapore (SG) is not supported.')).toBeInTheDocument();
    expect(screen.getByText('0.894')).toBeInTheDocument();
    const category = screen.getByLabelText(/^Category/);
    expect(
      within(category)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Select a category', 'Gaming', 'Music', 'Sports']);
    expect(
      within(screen.getByLabelText(/^Country/)).getByRole('option', { name: 'India (IN)' }),
    ).toBeInTheDocument();
    expect(screen.getByText('No prediction yet')).toBeInTheDocument();
    expect(api.calls('/api/v1/predictions')).toHaveLength(0);
  });

  it('labels every input of the PredictionRequest schema', async () => {
    mockApi();
    renderApp('/predictions');
    for (const label of [
      /^Title/,
      /^Description/,
      /^Tags/,
      /^Duration/,
      /^Channel name/,
      /^Subscribers/,
      /^Videos on channel/,
      /^Total channel views/,
      /^Category/,
      /^Country/,
    ]) {
      expect(await screen.findByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/^Title/)).toHaveAttribute('aria-required', 'true');
    expect(screen.getByLabelText(/^Description/)).toHaveAttribute('aria-required', 'false');
  });

  it('validates on the client before sending anything', async () => {
    const api = mockApi();
    const { user } = renderApp('/predictions');
    await screen.findByLabelText(/^Title/);
    await submit(user);
    expect(screen.getByLabelText(/^Title/)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/^Title/)).toHaveFocus();
    expect(screen.getByText('Select a category.')).toBeInTheDocument();
    expect(screen.getByText('Select a country.')).toBeInTheDocument();
    expect(api.calls('/api/v1/predictions')).toHaveLength(0);
  });

  it('submits the exact request, shows the submitting state, then the result', async () => {
    mockApi();
    let body: unknown;
    let url = '';
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.post(PREDICT_URL, async ({ request }) => {
        url = request.url;
        body = await request.json();
        await gate;
        return HttpResponse.json(predictionResponse());
      }),
    );
    const { user } = renderApp('/predictions?country=US&start_date=2025-12-10');
    await fillValidForm(user);
    await submit(user);

    const pending = await screen.findByRole('button', { name: 'Scoring…' });
    expect(pending).toBeDisabled();
    expect(screen.getByText('Scoring the video…')).toBeInTheDocument();
    release();

    expect(
      await screen.findByRole('heading', { name: 'High-performance probability' }),
    ).toHaveFocus();
    expect(screen.getByText('93.9%')).toBeInTheDocument();
    expect(screen.getByText('81.5%')).toBeInTheDocument();
    expect(screen.getByText('82.1%')).toBeInTheDocument();
    expect(screen.getByText('56.3%')).toBeInTheDocument();
    expect(screen.getByText('India (IN)', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('Sports', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Score video' })).toBeEnabled();

    // Exactly the PredictionRequest fields; dashboard filters are not sent.
    expect(new URL(url).search).toBe('');
    expect(body).toEqual({
      title: 'Last over thriller | Highlights!',
      description: '',
      tags: ['cricket', 'highlights'],
      channel_title: 'Star Sports',
      category: 'Sports',
      country: 'IN',
      duration_sec: 140,
      channel_subscriber_count: 8800000,
      channel_video_count: 14200,
      channel_view_count: 19600000000,
    });
  });

  it('never describes the score as a chance of becoming trending', async () => {
    mockApi();
    const { user } = renderApp('/predictions');
    await fillValidForm(user);
    await submit(user);
    await screen.findByText('93.9%');
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(
      /probability of becoming trending|will become trending|chance of trending|will_trend/i,
    );
    expect(text).toMatch(/High-performance probability/);
  });

  it('shows backend validation errors on the matching field', async () => {
    mockApi();
    server.use(
      http.post(PREDICT_URL, () =>
        errorEnvelope('invalid_prediction_input', 'country: unsupported country', 422, 'country', [
          { field: 'country', message: "unsupported country 'IN'. Supported countries: AU, CA" },
        ]),
      ),
    );
    const { user } = renderApp('/predictions');
    await fillValidForm(user);
    await submit(user);
    expect(await screen.findByText('Some inputs need attention')).toBeInTheDocument();
    expect(screen.getByText(/unsupported country 'IN'/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Country/)).toHaveAttribute('aria-invalid', 'true');
  });

  it('offers a retry for transient failures and resends the same request', async () => {
    mockApi();
    let attempts = 0;
    const bodies: unknown[] = [];
    server.use(
      http.post(PREDICT_URL, async ({ request }) => {
        attempts += 1;
        bodies.push(await request.json());
        return attempts === 1 ? HttpResponse.error() : HttpResponse.json(predictionResponse(0.5));
      }),
    );
    const { user } = renderApp('/predictions');
    await fillValidForm(user);
    await submit(user);
    expect(await screen.findByText("Can't reach the API")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('50.0%')).toBeInTheDocument();
    expect(bodies[1]).toEqual(bodies[0]);
  });

  it('explains when the model is unavailable for a prediction', async () => {
    mockApi();
    server.use(
      http.post(PREDICT_URL, () =>
        errorEnvelope('model_unavailable', 'The prediction model is not available.', 503),
      ),
    );
    const { user } = renderApp('/predictions');
    await fillValidForm(user);
    await submit(user);
    expect(await screen.findByText('The prediction model is unavailable')).toBeInTheDocument();
    expect(screen.getByText('Reference: req-test-1')).toBeInTheDocument();
  });

  it('shows an unavailable state when model info cannot be loaded', async () => {
    mockApi();
    server.use(
      http.get(`${BASE}/api/v1/predictions/model-info`, () =>
        errorEnvelope('model_unavailable', 'The prediction model is disabled.', 503),
      ),
    );
    renderApp('/predictions');
    expect(await screen.findByText('The prediction model is unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Score video' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument();
  });

  it('keeps global filters in the URL when navigating away and back', async () => {
    mockApi();
    const { user, location } = renderApp('/predictions?country=IN');
    await screen.findByRole('heading', { level: 1, name: 'ML predictions' });
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    await user.click(within(nav).getByRole('link', { name: 'Overview' }));
    await waitFor(() => expect(location().pathname).toBe('/'));
    expect(new URLSearchParams(location().search).getAll('country')).toEqual(['IN']);
  });
});
