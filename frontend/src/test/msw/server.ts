import { setupServer } from 'msw/node';

import { handlers } from './handlers';

/** Mock API server for tests. Requests without a matching handler fail the test. */
export const server = setupServer(...handlers);
