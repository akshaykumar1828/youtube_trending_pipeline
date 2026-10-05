import * as Tabs from '@radix-ui/react-tabs';
import { useSearchParams } from 'react-router';

import { PageHeader } from '../../layouts/PageHeader';
import { FilterBar } from '../filters/FilterBar';
import { useGlobalFilters } from '../filters/useGlobalFilters';
import { CategoriesPanel } from './CategoriesPanel';
import { ChannelsPanel } from './ChannelsPanel';
import { CountriesPanel } from './CountriesPanel';
import { EngagementPanel } from './EngagementPanel';

const TABS = [
  { value: 'categories', label: 'Categories' },
  { value: 'countries', label: 'Countries' },
  { value: 'engagement', label: 'Engagement' },
  { value: 'channels', label: 'Channels' },
] as const;
type Tab = (typeof TABS)[number]['value'];

function isTab(value: string | null): value is Tab {
  return TABS.some((t) => t.value === value);
}

/**
 * Analytics workspace. The active tab lives in the URL (?tab=…); Radix only mounts the active
 * panel, so only the visible section's endpoint is requested.
 */
export function AnalyticsPage() {
  const { filters } = useGlobalFilters();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab');
  const tab: Tab = isTab(requested) ? requested : 'categories';

  const selectTab = (value: string) =>
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('tab', value);
      return next;
    });

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Category, country, engagement and channel analysis for the selected period."
      />
      <FilterBar />
      <Tabs.Root value={tab} onValueChange={selectTab} className="space-y-4">
        <Tabs.List
          aria-label="Analytics sections"
          className="flex gap-1 overflow-x-auto border-b border-slate-200"
        >
          {TABS.map((t) => (
            <Tabs.Trigger
              key={t.value}
              value={t.value}
              className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm font-medium whitespace-nowrap text-slate-600 hover:text-slate-900 data-[state=active]:border-accent-600 data-[state=active]:text-accent-700"
            >
              {t.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="categories">
          <CategoriesPanel filters={filters} />
        </Tabs.Content>
        <Tabs.Content value="countries">
          <CountriesPanel filters={filters} />
        </Tabs.Content>
        <Tabs.Content value="engagement">
          <EngagementPanel filters={filters} />
        </Tabs.Content>
        <Tabs.Content value="channels">
          <ChannelsPanel filters={filters} />
        </Tabs.Content>
      </Tabs.Root>
    </>
  );
}
