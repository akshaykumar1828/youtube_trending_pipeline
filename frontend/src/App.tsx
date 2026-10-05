import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { createBrowserRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

type Router = ReturnType<typeof createBrowserRouter>;

/** Application providers: server state (TanStack Query) and routing. */
export default function App({ router, queryClient }: { router: Router; queryClient: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
