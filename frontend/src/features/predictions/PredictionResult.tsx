import { AlertTriangle, Gauge } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { isApiError } from '../../api/errors';
import type { Prediction } from '../../api/types';
import { describeError } from '../../components/data/describeError';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatRate } from '../../lib/format';
import { isValidationError } from './form';

const COMPONENTS: { key: keyof Prediction['components']; label: string }[] = [
  { key: 'text', label: 'Text score' },
];

function ScoreBar({ value, strong = false }: { value: number; strong?: boolean }) {
  return (
    <div aria-hidden="true" className="h-1.5 w-full rounded-sm bg-slate-100">
      <div
        className={strong ? 'h-full rounded-sm bg-accent-600' : 'h-full rounded-sm bg-slate-400'}
        style={{ width: `${Math.min(Math.max(value, 0), 1) * 100}%` }}
      />
    </div>
  );
}

interface PredictionResultProps {
  status: 'idle' | 'pending' | 'error' | 'success';
  data: Prediction | undefined;
  error: unknown;
  formErrors: string[];
  componentDescriptions: Record<string, string>;
  countryNames: Record<string, string>;
  onRetry: () => void;
}

export function PredictionResult({
  status,
  data,
  error,
  formErrors,
  componentDescriptions,
  countryNames,
  onRetry,
}: PredictionResultProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (status === 'success') headingRef.current?.focus();
  }, [status, data]);

  if (status === 'idle') {
    return (
      <div className="flex flex-col items-center px-6 py-12 text-center">
        <Gauge aria-hidden="true" className="size-6 text-slate-400" />
        <p className="mt-2 text-sm font-medium text-slate-800">No prediction yet</p>
        <p className="mt-1 max-w-xs text-xs text-slate-500">
          Fill in the form and select “Score video”. Nothing is scored until you submit.
        </p>
      </div>
    );
  }

  if (status === 'pending') {
    return (
      <div role="status" className="space-y-3 p-4">
        <span className="sr-only">Scoring the video…</span>
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-9 w-28" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (status === 'error') {
    if (isValidationError(error)) {
      return (
        <div role="alert" className="flex flex-col items-center px-6 py-10 text-center">
          <AlertTriangle aria-hidden="true" className="size-6 text-amber-500" />
          <p className="mt-2 text-sm font-medium text-slate-800">Some inputs need attention</p>
          <p className="mt-1 max-w-xs text-xs text-slate-600">
            The fields marked in the form were rejected by the model service.
          </p>
          {formErrors.map((message) => (
            <p key={message} className="mt-1 text-xs text-slate-600">
              {message}
            </p>
          ))}
        </div>
      );
    }
    const unavailable = isApiError(error) && error.code === 'model_unavailable';
    const described = describeError(error);
    return (
      <div role="alert" className="flex flex-col items-center px-6 py-10 text-center">
        <AlertTriangle aria-hidden="true" className="size-6 text-amber-500" />
        <p className="mt-2 text-sm font-medium text-slate-800">
          {unavailable ? 'The prediction model is unavailable' : described.title}
        </p>
        <p className="mt-1 max-w-xs text-xs text-slate-600">
          {unavailable
            ? 'The rest of the dashboard keeps working. Please try again later.'
            : described.message}
        </p>
        {described.canRetry && (
          <Button size="sm" className="mt-3" onClick={onRetry}>
            Retry
          </Button>
        )}
        {described.requestId && (
          <p className="mt-3 font-mono text-[11px] text-slate-500">
            Reference: {described.requestId}
          </p>
        )}
      </div>
    );
  }

  if (!data) return null;
  const { inputs_used: used } = data;
  return (
    <div className="space-y-5 p-4">
      <div>
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="text-xs font-medium text-slate-500 outline-none"
        >
          High-performance probability
        </h2>
        <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-900 tabular-nums">
          {formatRate(data.high_performance_probability, 1)}
        </p>
        <div className="mt-2">
          <ScoreBar value={data.high_performance_probability} strong />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Likelihood that the video, if it is trending, performs at or above its country’s
          thresholds for views, likes and comments.
        </p>
      </div>

      <section aria-labelledby="components-heading">
        <h3 id="components-heading" className="text-xs font-semibold text-slate-700">
          What the text alone suggests
        </h3>
        <dl className="mt-2 space-y-3">
          {COMPONENTS.map(({ key, label }) => (
            <div key={key}>
              <div className="flex justify-between text-xs">
                <dt className="text-slate-700">{label}</dt>
                <dd className="font-medium text-slate-900 tabular-nums">
                  {formatRate(data.components[key], 1)}
                </dd>
              </div>
              <div className="mt-1">
                <ScoreBar value={data.components[key]} />
              </div>
              {componentDescriptions[key] && (
                <p className="mt-1 text-[11px] text-slate-500">{componentDescriptions[key]}</p>
              )}
            </div>
          ))}
        </dl>
      </section>

      <dl className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-xs">
        <div>
          <dt className="text-slate-500">Category used</dt>
          <dd className="mt-0.5 font-medium text-slate-900">{used.category}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Country used</dt>
          <dd className="mt-0.5 font-medium text-slate-900">
            {countryNames[used.country]
              ? `${countryNames[used.country]} (${used.country})`
              : used.country}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-slate-500">Model version</dt>
          <dd className="mt-0.5 font-mono text-slate-700">{data.model.version}</dd>
        </div>
      </dl>
      <p className="text-[11px] leading-relaxed text-slate-500">{data.model.label_definition}</p>
    </div>
  );
}
