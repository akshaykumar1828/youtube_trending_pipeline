import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './msw/server';

// Pages are lazy-loaded; the first import of a page (and Recharts) in a cold test run can take
// longer than Testing Library's 1 s default wait.
configure({ asyncUtilTimeout: 5000 });

// jsdom has no layout engine or ResizeObserver. Recharts' ResponsiveContainer (and Radix's popper)
// observe their container size; report a fixed desktop-like size so charts render their SVG.
class ResizeObserverStub {
  private readonly callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    const entry = {
      target,
      contentRect: { width: 800, height: 300 },
    } as unknown as ResizeObserverEntry;
    this.callback([entry], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}
if (typeof window !== 'undefined' && !('ResizeObserver' in window)) {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// Any request without an MSW handler is an error: tests never reach a real network.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
