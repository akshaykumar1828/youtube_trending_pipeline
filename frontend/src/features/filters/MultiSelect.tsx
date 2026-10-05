import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';

import { cn } from '../../lib/cn';

export interface Option {
  value: string;
  label: string;
  hint?: string;
}

interface MultiSelectProps {
  label: string;
  options: Option[];
  values: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
  allLabel: string;
}

/** Popover with native checkboxes (keyboard and screen-reader friendly). Empty selection = all. */
export function MultiSelect({
  label,
  options,
  values,
  onChange,
  disabled,
  allLabel,
}: MultiSelectProps) {
  const selected = new Set(values);
  const summary =
    values.length === 0
      ? allLabel
      : values.length === 1
        ? (options.find((o) => o.value === values[0])?.label ?? values[0])
        : `${values.length} selected`;

  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(options.map((o) => o.value).filter((v) => next.has(v)));
  };

  return (
    <Popover.Root>
      <Popover.Trigger
        disabled={disabled}
        className={cn(
          'inline-flex h-8 max-w-56 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 text-xs text-slate-800 hover:border-slate-400 disabled:cursor-not-allowed disabled:text-slate-400',
          values.length > 0 && 'border-accent-500 text-accent-700',
        )}
      >
        <span className="text-slate-500">{label}:</span>
        <span className="truncate font-medium">{summary}</span>
        <ChevronDown aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={4}
          className="z-50 w-64 rounded-md border border-slate-200 bg-white shadow-sm"
        >
          <fieldset>
            <legend className="flex w-full items-center justify-between border-b border-slate-100 px-3 py-2 text-xs font-medium text-slate-700">
              {label}
            </legend>
            <div className="max-h-64 overflow-y-auto p-1">
              {options.map((option) => (
                <label
                  key={option.value}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    className="size-3.5 accent-accent-600"
                    checked={selected.has(option.value)}
                    onChange={() => toggle(option.value)}
                  />
                  <span className="flex-1 truncate">{option.label}</span>
                  {option.hint && (
                    <span className="font-mono text-[11px] text-slate-500">{option.hint}</span>
                  )}
                </label>
              ))}
            </div>
          </fieldset>
          {values.length > 0 && (
            <div className="border-t border-slate-100 p-1">
              <button
                type="button"
                onClick={() => onChange([])}
                className="w-full rounded px-2 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-50"
              >
                Clear selection ({allLabel.toLowerCase()})
              </button>
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
