import type { FilterParams } from '../../api/types';

/** The global filter query parameters, named exactly as the backend expects them. */
export const FILTER_KEYS = ['start_date', 'end_date', 'country', 'category'] as const;

function values(params: URLSearchParams, key: string): string[] {
  return params
    .getAll(key)
    .map((v) => v.trim())
    .filter(Boolean);
}

/** URL -> filters. Values are passed through as-is: the backend validates them. */
export function readFilters(params: URLSearchParams): FilterParams {
  const filters: FilterParams = {};
  const start = params.get('start_date')?.trim();
  const end = params.get('end_date')?.trim();
  if (start) filters.start_date = start;
  if (end) filters.end_date = end;
  const country = values(params, 'country');
  const category = values(params, 'category');
  if (country.length) filters.country = country;
  if (category.length) filters.category = category;
  return filters;
}

/** Returns a copy of `current` with the filter keys replaced by `filters` (other params kept). */
export function writeFilters(current: URLSearchParams, filters: FilterParams): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const key of FILTER_KEYS) next.delete(key);
  if (filters.start_date) next.set('start_date', filters.start_date);
  if (filters.end_date) next.set('end_date', filters.end_date);
  for (const c of filters.country ?? []) next.append('country', c);
  for (const c of filters.category ?? []) next.append('category', c);
  return next;
}

/** Only the filter part of a query string ("?country=IN&…" or ""), for links between pages. */
export function filterSearch(params: URLSearchParams): string {
  const only = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    for (const value of params.getAll(key)) only.append(key, value);
  }
  const search = only.toString();
  return search ? `?${search}` : '';
}
