import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

import { formatInteger } from '../../lib/format';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  pageSizeOptions: readonly number[];
  itemLabel: string;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

/** Server-side pagination controls driven by the API's page/total/total_pages. */
export function Pagination({
  page,
  pageSize,
  total,
  totalPages,
  pageSizeOptions,
  itemLabel,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const canPrev = page > 1;
  const canNext = page < totalPages;
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3"
    >
      <p className="text-xs text-slate-600" aria-live="polite">
        {total === 0
          ? `No ${itemLabel}`
          : `Showing ${formatInteger(first)}–${formatInteger(last)} of ${formatInteger(total)} ${itemLabel}`}
      </p>
      <div className="flex items-center gap-3">
        <Select
          label="Rows per page"
          showLabel
          value={String(pageSize)}
          options={pageSizeOptions.map((n) => ({ value: String(n), label: String(n) }))}
          onChange={(value) => onPageSizeChange(Number(value))}
        />
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            aria-label="First page"
            disabled={!canPrev}
            onClick={() => onPageChange(1)}
          >
            <ChevronsLeft aria-hidden="true" className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Previous page"
            disabled={!canPrev}
            onClick={() => onPageChange(page - 1)}
          >
            <ChevronLeft aria-hidden="true" className="size-4" />
          </Button>
          <span className="px-1 text-xs text-slate-600 tabular-nums">
            Page {formatInteger(page)} of {formatInteger(Math.max(totalPages, 1))}
          </span>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Next page"
            disabled={!canNext}
            onClick={() => onPageChange(page + 1)}
          >
            <ChevronRight aria-hidden="true" className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Last page"
            disabled={!canNext}
            onClick={() => onPageChange(totalPages)}
          >
            <ChevronsRight aria-hidden="true" className="size-4" />
          </Button>
        </div>
      </div>
    </nav>
  );
}
