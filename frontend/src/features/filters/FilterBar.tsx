import { RotateCcw } from 'lucide-react';
import { useId } from 'react';

import { Button } from '../../components/ui/Button';
import { formatDate } from '../../lib/format';
import { MultiSelect } from './MultiSelect';
import { useFilterOptions } from './useFilterOptions';
import { useGlobalFilters } from './useGlobalFilters';

function DateField({
  label,
  value,
  min,
  max,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  min?: string;
  max?: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-1.5">
      <label htmlFor={id} className="text-xs text-slate-500">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-800 tabular-nums hover:border-slate-400"
      />
    </div>
  );
}

/**
 * Global filters (date range, countries, categories) written to the URL. Options and limits
 * come from /meta/filters; the backend validates and applies defaults.
 */
export function FilterBar() {
  const { filters, updateFilters, clearFilters, hasFilters } = useGlobalFilters();
  const options = useFilterOptions();
  const meta = options.data;
  const usingDefaultDates = !filters.start_date && !filters.end_date;

  return (
    <section
      aria-label="Filters"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5"
    >
      <DateField
        label="From"
        value={filters.start_date ?? meta?.default_range.start_date ?? ''}
        min={meta?.date_range.min_date}
        max={meta?.date_range.max_date}
        disabled={!meta}
        onChange={(value) => updateFilters({ start_date: value || null })}
      />
      <DateField
        label="To"
        value={filters.end_date ?? meta?.default_range.end_date ?? ''}
        min={meta?.date_range.min_date}
        max={meta?.date_range.max_date}
        disabled={!meta}
        onChange={(value) => updateFilters({ end_date: value || null })}
      />
      <MultiSelect
        label="Countries"
        allLabel="All countries"
        disabled={!meta}
        options={(meta?.countries ?? []).map((c) => ({
          value: c.code,
          label: c.name,
          hint: c.code,
        }))}
        values={filters.country ?? []}
        onChange={(country) => updateFilters({ country })}
      />
      <MultiSelect
        label="Categories"
        allLabel="All categories"
        disabled={!meta}
        options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))}
        values={filters.category ?? []}
        onChange={(category) => updateFilters({ category })}
      />
      {hasFilters && (
        <Button size="sm" variant="ghost" onClick={clearFilters}>
          <RotateCcw aria-hidden="true" className="size-3.5" />
          Reset filters
        </Button>
      )}
      <p className="ml-auto text-xs text-slate-500" aria-live="polite">
        {options.isError
          ? 'Filter options are unavailable.'
          : meta && usingDefaultDates
            ? `Default window: latest 30 days of data (to ${formatDate(meta.date_range.max_date)})`
            : null}
      </p>
    </section>
  );
}
