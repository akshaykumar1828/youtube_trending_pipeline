import type { ReactNode } from 'react';

import { cn } from '../../lib/cn';

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  align?: 'left' | 'right';
  /** Extra classes for header and cells, e.g. 'hidden md:table-cell' to simplify small screens. */
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  /** Describes the table for screen readers. */
  caption: string;
}

/** Semantic table with a sticky header; scrolls horizontally inside its container on small screens. */
export function DataTable<T>({ columns, rows, rowKey, caption }: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  'px-4 py-2 text-xs font-medium whitespace-nowrap text-slate-500',
                  column.align === 'right' ? 'text-right' : 'text-left',
                  column.className,
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={rowKey(row)} className="hover:bg-slate-50">
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn(
                    'px-4 py-2.5 align-middle text-slate-700',
                    column.align === 'right' && 'text-right tabular-nums',
                    column.className,
                  )}
                >
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
