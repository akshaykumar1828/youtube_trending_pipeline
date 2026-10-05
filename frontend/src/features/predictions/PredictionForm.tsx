import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react';

import type { ModelInfo, PredictionRequest } from '../../api/types';
import { Button } from '../../components/ui/Button';
import { cn } from '../../lib/cn';
import { formatDuration } from '../../lib/format';
import {
  EMPTY_FORM,
  parseTags,
  PREDICTION_LIMITS as L,
  toPredictionRequest,
  validatePrediction,
  type FieldErrors,
  type PredictionField,
  type PredictionFormValues,
} from './form';

const inputClass =
  'block w-full rounded-md border bg-white px-2.5 text-sm text-slate-900 placeholder:text-slate-500 disabled:bg-slate-50 disabled:text-slate-400';

function Field({
  name,
  label,
  hint,
  error,
  required,
  children,
}: {
  name: PredictionField;
  label: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: (props: {
    id: string;
    name: PredictionField;
    'aria-required': boolean;
    'aria-invalid': boolean;
    'aria-describedby': string | undefined;
    className: string;
  }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-xs font-medium text-slate-700">
        {label}
        {required ? (
          <span aria-hidden="true" className="text-rose-600">
            {' '}
            *
          </span>
        ) : (
          <span className="font-normal text-slate-500"> (optional)</span>
        )}
      </label>
      <div className="mt-1">
        {children({
          id,
          name,
          'aria-required': Boolean(required),
          'aria-invalid': Boolean(error),
          'aria-describedby': [hintId, errorId].filter(Boolean).join(' ') || undefined,
          className: cn(
            inputClass,
            error ? 'border-rose-400' : 'border-slate-300 hover:border-slate-400',
          ),
        })}
      </div>
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

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="min-w-0 space-y-3">
      <legend className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

interface PredictionFormProps {
  modelInfo: ModelInfo;
  countryNames: Record<string, string>;
  serverErrors: FieldErrors;
  isSubmitting: boolean;
  onSubmit: (request: PredictionRequest) => void;
}

/** Inputs of the existing PredictionRequest schema; nothing more. */
export function PredictionForm({
  modelInfo,
  countryNames,
  serverErrors,
  isSubmitting,
  onSubmit,
}: PredictionFormProps) {
  const [values, setValues] = useState<PredictionFormValues>(EMPTY_FORM);
  const [clientErrors, setClientErrors] = useState<FieldErrors>({});
  const formRef = useRef<HTMLFormElement>(null);
  const errors = { ...serverErrors, ...clientErrors };

  const set = (field: PredictionField) => (value: string) => {
    setValues((v) => ({ ...v, [field]: value }));
    setClientErrors((e) => ({ ...e, [field]: undefined }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found = validatePrediction(values);
    setClientErrors(found);
    const first = Object.keys(found)[0];
    if (first) {
      formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }
    onSubmit(toPredictionRequest(values));
  };

  const duration = Number(values.duration_sec);
  const tagCount = parseTags(values.tags).length;

  return (
    <form
      ref={formRef}
      noValidate
      onSubmit={submit}
      aria-label="Prediction inputs"
      className="space-y-6 p-4"
    >
      <Section title="Video">
        <Field name="title" label="Title" required error={errors.title}>
          {(p) => (
            <input
              {...p}
              className={cn(p.className, 'h-9')}
              value={values.title}
              maxLength={L.title}
              onChange={(e) => set('title')(e.target.value)}
            />
          )}
        </Field>
        <Field name="description" label="Description" error={errors.description}>
          {(p) => (
            <textarea
              {...p}
              className={cn(p.className, 'min-h-24 py-2')}
              value={values.description}
              maxLength={L.description}
              onChange={(e) => set('description')(e.target.value)}
            />
          )}
        </Field>
        <Field
          name="tags"
          label="Tags"
          hint={`Separate tags with commas (${tagCount} of up to ${L.tags}).`}
          error={errors.tags}
        >
          {(p) => (
            <input
              {...p}
              className={cn(p.className, 'h-9')}
              value={values.tags}
              onChange={(e) => set('tags')(e.target.value)}
            />
          )}
        </Field>
        <Field
          name="duration_sec"
          label="Duration (seconds)"
          required
          hint={
            values.duration_sec && Number.isFinite(duration) && duration >= 0
              ? `= ${formatDuration(duration)}`
              : undefined
          }
          error={errors.duration_sec}
        >
          {(p) => (
            <input
              {...p}
              className={cn(p.className, 'h-9 tabular-nums')}
              type="number"
              inputMode="decimal"
              min={0}
              max={L.duration_sec}
              value={values.duration_sec}
              onChange={(e) => set('duration_sec')(e.target.value)}
            />
          )}
        </Field>
      </Section>

      <Section title="Channel">
        <Field name="channel_title" label="Channel name" error={errors.channel_title}>
          {(p) => (
            <input
              {...p}
              className={cn(p.className, 'h-9')}
              value={values.channel_title}
              maxLength={L.channel_title}
              onChange={(e) => set('channel_title')(e.target.value)}
            />
          )}
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          {(
            [
              ['channel_subscriber_count', 'Subscribers', L.channel_subscriber_count],
              ['channel_video_count', 'Videos on channel', L.channel_video_count],
              ['channel_view_count', 'Total channel views', L.channel_view_count],
            ] as const
          ).map(([field, label, max]) => (
            <Field key={field} name={field} label={label} required error={errors[field]}>
              {(p) => (
                <input
                  {...p}
                  className={cn(p.className, 'h-9 tabular-nums')}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={max}
                  step={1}
                  value={values[field]}
                  onChange={(e) => set(field)(e.target.value)}
                />
              )}
            </Field>
          ))}
        </div>
      </Section>

      <Section title="Context">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            name="category"
            label="Category"
            required
            hint="Categories the model was trained on."
            error={errors.category}
          >
            {(p) => (
              <select
                {...p}
                className={cn(p.className, 'h-9')}
                value={values.category}
                onChange={(e) => set('category')(e.target.value)}
              >
                <option value="">Select a category</option>
                {modelInfo.supported_categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field
            name="country"
            label="Country"
            required
            hint="Countries the model was trained on."
            error={errors.country}
          >
            {(p) => (
              <select
                {...p}
                className={cn(p.className, 'h-9')}
                value={values.country}
                onChange={(e) => set('country')(e.target.value)}
              >
                <option value="">Select a country</option>
                {modelInfo.supported_countries.map((code) => (
                  <option key={code} value={code}>
                    {countryNames[code] ? `${countryNames[code]} (${code})` : code}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
      </Section>

      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
        <Button type="submit" variant="primary" disabled={isSubmitting}>
          {isSubmitting ? 'Scoring…' : 'Score video'}
        </Button>
        <Button
          variant="ghost"
          disabled={isSubmitting}
          onClick={() => {
            setValues(EMPTY_FORM);
            setClientErrors({});
          }}
        >
          Clear form
        </Button>
        <p className="text-xs text-slate-500">
          <span aria-hidden="true" className="text-rose-600">
            *
          </span>{' '}
          Required
        </p>
      </div>
    </form>
  );
}
