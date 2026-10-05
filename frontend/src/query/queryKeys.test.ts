// @vitest-environment node
import { hashKey } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';

import { normalizeFilters, queryKeys } from './queryKeys';

describe('normalizeFilters', () => {
  it('sorts and de-duplicates arrays without otherwise changing values', () => {
    expect(
      normalizeFilters({
        start_date: '2025-12-01',
        country: ['US', 'IN', 'US'],
        category: ['Music', 'Comedy'],
      }),
    ).toEqual({ start_date: '2025-12-01', country: ['IN', 'US'], category: ['Comedy', 'Music'] });
    // Case is not normalized: the backend is the authority for validation/normalization.
    expect(normalizeFilters({ country: ['in'] })).toEqual({ country: ['in'] });
  });

  it('drops empty and null values', () => {
    expect(
      normalizeFilters({ start_date: null, end_date: '', country: [], category: null }),
    ).toEqual({});
    expect(normalizeFilters()).toEqual({});
  });

  it('does not mutate its input', () => {
    const country = ['US', 'IN'];
    normalizeFilters({ country });
    expect(country).toEqual(['US', 'IN']);
  });
});

describe('queryKeys', () => {
  it('produces identical cache hashes for equivalent filters', () => {
    const a = queryKeys.overview.kpis({ country: ['US', 'IN'], category: ['Music'] });
    const b = queryKeys.overview.kpis({ country: ['IN', 'US', 'IN'], category: ['Music'] });
    expect(hashKey(a)).toBe(hashKey(b));
    expect(hashKey(queryKeys.overview.kpis({ country: [] }))).toBe(
      hashKey(queryKeys.overview.kpis()),
    );
  });

  it('distinguishes different filters and parameters', () => {
    const keys = [
      queryKeys.overview.kpis(),
      queryKeys.overview.kpis({ country: ['IN'] }),
      queryKeys.overview.kpis({ start_date: '2025-12-01' }),
      queryKeys.overview.dailyVolume(),
      queryKeys.overview.dailyVolume({}, { split_by: 'country' }),
      queryKeys.analytics.categories(),
      queryKeys.analytics.countries(),
      queryKeys.analytics.engagement({}, { scatter_limit: 100 }),
      queryKeys.analytics.channels({}, { sort: 'views', limit: 10 }),
      queryKeys.videos.list({}, { page: 1, page_size: 25 }),
      queryKeys.videos.list({}, { page: 2, page_size: 25 }),
      queryKeys.videos.detail('abc'),
      queryKeys.videos.history('abc'),
      queryKeys.meta.filters(),
      queryKeys.predictions.modelInfo(),
    ];
    expect(new Set(keys.map((k) => hashKey(k))).size).toBe(keys.length);
  });

  it('includes the global filters in every filtered key', () => {
    const filters = { country: ['IN'] };
    const filtered = [
      queryKeys.overview.kpis(filters),
      queryKeys.overview.dailyVolume(filters),
      queryKeys.analytics.categories(filters),
      queryKeys.analytics.countries(filters),
      queryKeys.analytics.engagement(filters),
      queryKeys.analytics.channels(filters),
      queryKeys.videos.list(filters),
    ];
    for (const key of filtered) expect(key[2]).toEqual({ country: ['IN'] });
  });

  it('treats omitted and undefined endpoint parameters the same', () => {
    expect(hashKey(queryKeys.videos.list({}, { sort: 'views', search: undefined }))).toBe(
      hashKey(queryKeys.videos.list({}, { sort: 'views' })),
    );
  });

  it('is hierarchical so groups can be invalidated', () => {
    expect(queryKeys.overview.kpis().slice(0, 1)).toEqual(queryKeys.overview.all);
    expect(queryKeys.analytics.channels().slice(0, 1)).toEqual(queryKeys.analytics.all);
    expect(queryKeys.videos.detail('x').slice(0, 1)).toEqual(queryKeys.videos.all);
    expect(queryKeys.meta.filters().slice(0, 1)).toEqual(queryKeys.meta.all);
    expect(queryKeys.predictions.modelInfo().slice(0, 1)).toEqual(queryKeys.predictions.all);
  });

  it('is stable across calls and JSON-serializable', () => {
    const key = queryKeys.videos.list({ country: ['IN'] }, { sort: 'likes', order: 'asc' });
    expect(queryKeys.videos.list({ country: ['IN'] }, { sort: 'likes', order: 'asc' })).toEqual(
      key,
    );
    expect(JSON.parse(JSON.stringify(key))).toEqual(key);
  });
});
