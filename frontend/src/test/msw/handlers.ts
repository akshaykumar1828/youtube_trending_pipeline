import type { RequestHandler } from 'msw';

/**
 * Default request handlers shared by all tests. Intentionally empty in Phase 3.1:
 * API handlers are added with the API client in Phase 3.2. Individual tests can add
 * handlers with `server.use(...)`.
 */
export const handlers: RequestHandler[] = [];
