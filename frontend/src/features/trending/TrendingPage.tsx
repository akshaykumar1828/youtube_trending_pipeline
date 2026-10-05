import { ArrowDownWideNarrow, ArrowUpNarrowWide, Search, X } from 'lucide-react';
import type { FormEvent } from 'react';

import type { VideoSort } from '../../api/types';
import { ChartCard } from '../../components/data/ChartCard';
import { Pagination } from '../../components/data/Pagination';
import { QueryState } from '../../components/data/QueryState';
import { EmptyState, LoadingState, NoResultsState } from '../../components/data/states';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { PageHeader } from '../../layouts/PageHeader';
import { FilterBar } from '../filters/FilterBar';
import { useGlobalFilters } from '../filters/useGlobalFilters';
import { useVideoList } from '../videos/queries';
import { VideoTable } from '../videos/VideoTable';
import { PAGE_SIZES, SORT_LABELS, useVideoListParams } from './useVideoListParams';

const SORT_OPTIONS = (Object.keys(SORT_LABELS) as VideoSort[]).map((value) => ({
  value,
  label: SORT_LABELS[value],
}));

function SearchForm({ value, onSubmit }: { value: string; onSubmit: (value: string) => void }) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(String(new FormData(event.currentTarget).get('search') ?? ''));
  };
  return (
    <form role="search" onSubmit={submit} className="flex min-w-0 flex-1 items-center gap-2">
      <label htmlFor="video-search" className="sr-only">
        Search videos by title, channel or video ID
      </label>
      <div className="relative min-w-0 flex-1 sm:max-w-sm">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-2 left-2.5 size-4 text-slate-400"
        />
        <input
          key={value}
          id="video-search"
          name="search"
          type="search"
          defaultValue={value}
          minLength={2}
          maxLength={100}
          placeholder="Search title, channel or video ID"
          className="h-8 w-full rounded-md border border-slate-300 bg-white pr-2 pl-8 text-xs text-slate-800 placeholder:text-slate-500 hover:border-slate-400"
        />
      </div>
      <Button type="submit" size="sm">
        Search
      </Button>
      {value && (
        <Button size="sm" variant="ghost" onClick={() => onSubmit('')}>
          <X aria-hidden="true" className="size-3.5" />
          Clear
        </Button>
      )}
    </form>
  );
}

export function TrendingPage() {
  const { filters, search: filterSearch } = useGlobalFilters();
  const list = useVideoListParams();
  const videos = useVideoList(filters, list.apiParams);
  const { params } = list;

  return (
    <>
      <PageHeader
        title="Trending videos"
        description="Videos that trended in the selected period. Values come from each video's latest snapshot within the filters; sorting and paging happen on the server."
      />
      <FilterBar />
      <ChartCard
        title="Videos"
        actions={
          <div className="flex items-center gap-2">
            <Select
              label="Sort by"
              showLabel
              value={params.sort}
              options={SORT_OPTIONS}
              onChange={list.setSort}
            />
            <Button
              size="sm"
              variant="secondary"
              aria-label={
                params.order === 'desc'
                  ? 'Sorted descending; switch to ascending'
                  : 'Sorted ascending; switch to descending'
              }
              onClick={() => list.setOrder(params.order === 'desc' ? 'asc' : 'desc')}
            >
              {params.order === 'desc' ? (
                <ArrowDownWideNarrow aria-hidden="true" className="size-4" />
              ) : (
                <ArrowUpNarrowWide aria-hidden="true" className="size-4" />
              )}
              {params.order === 'desc' ? 'Desc' : 'Asc'}
            </Button>
          </div>
        }
      >
        <div className="border-b border-slate-100 px-4 py-3">
          <SearchForm value={params.search} onSubmit={list.setSearch} />
        </div>
        <QueryState query={videos} loading={<LoadingState rows={10} label="Loading videos" />}>
          {({ data }) => {
            if (data.items.length === 0) {
              if (data.total > 0) {
                return (
                  <EmptyState
                    title="This page is past the end of the results"
                    description={`There are ${data.total_pages} pages for this selection.`}
                    action={
                      <Button size="sm" onClick={() => list.setPage(1)}>
                        Go to the first page
                      </Button>
                    }
                  />
                );
              }
              return params.search ? (
                <NoResultsState
                  title={`No videos match “${params.search}”`}
                  description="Try another search term, or widen the filters."
                  action={
                    <Button size="sm" onClick={() => list.setSearch('')}>
                      Clear search
                    </Button>
                  }
                />
              ) : (
                <EmptyState
                  title="No videos match the current filters"
                  description="Try a wider date range or fewer countries and categories."
                />
              );
            }
            return (
              <>
                <VideoTable items={data.items} search={filterSearch} caption="Trending videos" />
                <Pagination
                  page={data.page}
                  pageSize={data.page_size}
                  total={data.total}
                  totalPages={data.total_pages}
                  pageSizeOptions={PAGE_SIZES}
                  itemLabel="videos"
                  onPageChange={list.setPage}
                  onPageSizeChange={list.setPageSize}
                />
              </>
            );
          }}
        </QueryState>
      </ChartCard>
    </>
  );
}
