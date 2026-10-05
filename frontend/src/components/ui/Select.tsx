import { useId, type SelectHTMLAttributes } from 'react';

import { cn } from '../../lib/cn';

interface SelectProps<T extends string> extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  'onChange' | 'value'
> {
  label: string;
  /** Show the label visually (otherwise it is available to screen readers only). */
  showLabel?: boolean;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}

/** Native select (fully keyboard and screen-reader accessible) with a label. */
export function Select<T extends string>({
  label,
  showLabel = false,
  value,
  options,
  onChange,
  className,
  ...props
}: SelectProps<T>) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className={showLabel ? 'text-xs font-medium text-slate-600' : 'sr-only'}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        className={cn(
          'h-8 rounded-md border border-slate-300 bg-white pr-7 pl-2.5 text-xs text-slate-800 hover:border-slate-400',
          className,
        )}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
