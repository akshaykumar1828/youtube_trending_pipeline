import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

import type { FilterParams } from '../../api/types';
import { filterSearch, readFilters, writeFilters } from './urlFilters';

/**
 * Global filters with the URL as the single source of truth. Query keys include these
 * filters, so changing them makes TanStack Query fetch the matching data automatically.
 */
export function useGlobalFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const search = useMemo(() => filterSearch(searchParams), [searchParams]);

  const setFilters = useCallback(
    (next: FilterParams) => {
      setSearchParams((previous) => {
        const params = writeFilters(previous, next);
        params.delete('page'); // a new filter set starts at the first page
        return params;
      });
    },
    [setSearchParams],
  );

  const updateFilters = useCallback(
    (patch: Partial<FilterParams>) => setFilters({ ...filters, ...patch }),
    [filters, setFilters],
  );

  const clearFilters = useCallback(() => setFilters({}), [setFilters]);

  return {
    filters,
    /** "?start_date=…&country=…" or "" — append to links to keep filters across pages. */
    search,
    hasFilters: search !== '',
    setFilters,
    updateFilters,
    clearFilters,
  };
}
