import { Link, useRouteError } from 'react-router';

import { Card } from '../components/ui/Card';
import { APP_NAME } from '../layouts/PageHeader';

export function NotFoundPage() {
  return (
    <Card className="px-6 py-12 text-center">
      <title>{`Page not found · ${APP_NAME}`}</title>
      <p className="text-sm font-semibold text-slate-900">Page not found</p>
      <p className="mt-1 text-sm text-slate-600">The page you requested does not exist.</p>
      <Link
        to="/"
        className="mt-4 inline-block text-sm font-medium text-accent-700 hover:underline"
      >
        Go to the overview
      </Link>
    </Card>
  );
}

/** Route-level error boundary: a friendly message, never a stack trace. */
export function RouteErrorPage() {
  const error = useRouteError();
  console.error(error);
  return (
    <Card role="alert" className="px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-900">This page could not be displayed</p>
      <p className="mt-1 text-sm text-slate-600">
        An unexpected error occurred. Reloading usually helps.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="mt-4 text-sm font-medium text-accent-700 hover:underline"
      >
        Reload the page
      </button>
    </Card>
  );
}

export function PageLoading() {
  return (
    <div role="status" className="p-6 text-sm text-slate-500">
      Loading…
    </div>
  );
}
