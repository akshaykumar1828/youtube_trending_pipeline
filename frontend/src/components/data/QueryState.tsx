import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { cn } from '../../lib/cn';
import { EmptyState, ErrorState, LoadingState } from './states';

export const NO_DATA_DESCRIPTION =
  'No data matches the current filters. Try a wider date range or fewer filters.';

interface QueryStateProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  /** When true, the empty state is shown instead of `children`. */
  isEmpty?: (data: T) => boolean;
  emptyTitle?: string;
  emptyDescription?: ReactNode;
  loading?: ReactNode;
  className?: string;
}

/**
 * Renders the loading, error, empty or success state of one query. While previous data is
 * shown during a refetch (keepPreviousData), the content is dimmed and marked aria-busy.
 */
export function QueryState<T>({
  query,
  children,
  isEmpty,
  emptyTitle = 'No data',
  emptyDescription = NO_DATA_DESCRIPTION,
  loading,
  className,
}: QueryStateProps<T>) {
  if (query.isPending) {
    return <>{loading ?? <LoadingState className={className} />}</>;
  }
  if (query.isError) {
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} className={className} />
    );
  }
  if (isEmpty?.(query.data)) {
    return <EmptyState title={emptyTitle} description={emptyDescription} className={className} />;
  }
  const refreshing = query.isFetching && query.isPlaceholderData;
  return (
    <div aria-busy={refreshing} className={cn('transition-opacity', refreshing && 'opacity-60')}>
      {children(query.data)}
    </div>
  );
}
