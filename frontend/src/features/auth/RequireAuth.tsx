import { ShieldAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, Navigate, useLocation } from 'react-router';

import type { Permission } from '../../api/types';
import { ErrorState } from '../../components/data/states';
import { Card } from '../../components/ui/Card';
import { APP_NAME } from '../../layouts/PageHeader';
import { hasPermission, loginPathFor, ROLE_LABELS } from './permissions';
import { useCurrentUser } from './queries';

/**
 * Renders its children only for a signed-in user; otherwise redirects to /login?next=<here>.
 * This is navigation UX: every protected API call is independently checked by the server.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  const currentUser = useCurrentUser();

  if (currentUser.data) return children;
  if (currentUser.isPending) {
    return (
      <div role="status" className="p-6 text-sm text-slate-500">
        Checking your session…
      </div>
    );
  }
  if (currentUser.isError) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Card>
          <ErrorState error={currentUser.error} onRetry={() => void currentUser.refetch()} />
        </Card>
      </div>
    );
  }
  return <Navigate to={loginPathFor(location)} replace />;
}

export function ForbiddenState({ message }: { message?: string }) {
  const currentUser = useCurrentUser();
  const role = currentUser.data?.user.role;
  return (
    <Card role="alert" className="px-6 py-12 text-center">
      <title>{`Access denied · ${APP_NAME}`}</title>
      <ShieldAlert aria-hidden="true" className="mx-auto size-6 text-amber-500" />
      <p className="mt-2 text-sm font-semibold text-slate-900">Access denied</p>
      <p className="mt-1 text-sm text-slate-600">
        {message ??
          `Your role${role ? ` (${ROLE_LABELS[role]})` : ''} does not include access to this page.`}
      </p>
      <Link
        to="/"
        className="mt-4 inline-block text-sm font-medium text-accent-700 hover:underline"
      >
        Go to the overview
      </Link>
    </Card>
  );
}

/** Shows the forbidden state instead of `children` when the user lacks `permission`. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const currentUser = useCurrentUser();
  if (!hasPermission(currentUser.data, permission)) return <ForbiddenState />;
  return children;
}
