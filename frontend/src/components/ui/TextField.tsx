import { useId, type InputHTMLAttributes, type ReactNode } from 'react';

import { cn } from '../../lib/cn';

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange'> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  error?: string;
}

/** Labelled text input with hint and error text wired up for screen readers. */
export function TextField({ label, hint, error, onChange, className, ...props }: TextFieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-xs font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'mt-1 block h-9 w-full rounded-md border bg-white px-2.5 text-sm text-slate-900 placeholder:text-slate-500 disabled:bg-slate-50',
          error ? 'border-rose-400' : 'border-slate-300 hover:border-slate-400',
          className,
        )}
        {...props}
      />
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1 text-xs font-medium text-rose-700">
          {error}
        </p>
      )}
    </div>
  );
}
