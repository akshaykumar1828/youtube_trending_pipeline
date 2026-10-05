import type { RouteObject } from 'react-router';

import { AuthLayout } from '../features/auth/AuthLayout';
import { RequireAuth } from '../features/auth/RequireAuth';
import { AppShell } from '../layouts/AppShell';
import { NotFoundPage, PageLoading, RouteErrorPage } from './pages';

/**
 * Application routes. Pages are lazy-loaded (separate chunks, so Recharts loads only with the
 * pages that use it). The error boundary sits inside the shell, so navigation stays usable.
 *
 * /login and /register are public. Everything inside the shell requires a session
 * (RequireAuth redirects to /login?next=…); the API enforces the same rule on every request.
 */
export const routes: RouteObject[] = [
  {
    element: <AuthLayout />,
    hydrateFallbackElement: <PageLoading />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        path: 'login',
        lazy: async () => ({
          Component: (await import('../features/auth/LoginPage')).LoginPage,
        }),
      },
      {
        path: 'register',
        lazy: async () => ({
          Component: (await import('../features/auth/RegisterPage')).RegisterPage,
        }),
      },
    ],
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    hydrateFallbackElement: <PageLoading />,
    children: [
      {
        errorElement: <RouteErrorPage />,
        children: [
          {
            index: true,
            lazy: async () => ({
              Component: (await import('../features/overview/OverviewPage')).OverviewPage,
            }),
          },
          {
            path: 'trending',
            lazy: async () => ({
              Component: (await import('../features/trending/TrendingPage')).TrendingPage,
            }),
          },
          {
            path: 'analytics',
            lazy: async () => ({
              Component: (await import('../features/analytics/AnalyticsPage')).AnalyticsPage,
            }),
          },
          {
            path: 'videos/:videoId',
            lazy: async () => ({
              Component: (await import('../features/videos/VideoDetailPage')).VideoDetailPage,
            }),
          },
          {
            path: 'predictions',
            lazy: async () => ({
              Component: (await import('../features/predictions/PredictionsPage')).PredictionsPage,
            }),
          },
          {
            path: 'team',
            lazy: async () => ({
              Component: (await import('../features/team/TeamPage')).TeamPage,
            }),
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
