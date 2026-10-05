import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { server } from './msw/server';

describe('MSW test server', () => {
  it('intercepts requests registered by a test', async () => {
    server.use(
      http.get('http://localhost:8000/health/live', () => HttpResponse.json({ status: 'ok' })),
    );
    const response = await fetch('http://localhost:8000/health/live');
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: 'ok' });
  });

  it('resets per-test handlers and blocks unhandled requests', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    await expect(fetch('http://localhost:8000/health/live')).rejects.toThrow();
    expect(consoleError).toHaveBeenCalled();
  });
});
