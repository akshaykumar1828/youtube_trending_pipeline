import { isApiError, type ApiError } from '../../api/errors';
import type { PredictionRequest } from '../../api/types';

const VALIDATION_CODES = new Set(['invalid_prediction_input', 'invalid_request']);

/** A 422 from the prediction API (request or model-input validation). */
export function isValidationError(error: unknown): error is ApiError {
  return isApiError(error) && VALIDATION_CODES.has(error.code);
}

/**
 * Input limits of PredictionRequest, used only for immediate form feedback. They mirror the
 * OpenAPI contract and a test compares them with frontend/openapi.json; the backend still
 * validates every request and its 422 errors are shown on the matching fields.
 */
export const PREDICTION_LIMITS = {
  title: 200,
  description: 5000,
  channel_title: 200,
  tags: 50,
  tag: 100,
  duration_sec: 604800,
  channel_subscriber_count: 10_000_000_000,
  channel_video_count: 100_000_000,
  channel_view_count: 10_000_000_000_000,
} as const;

/** Form state: one string per PredictionRequest field (tags as comma-separated text). */
export interface PredictionFormValues {
  title: string;
  description: string;
  tags: string;
  channel_title: string;
  category: string;
  country: string;
  duration_sec: string;
  channel_subscriber_count: string;
  channel_video_count: string;
  channel_view_count: string;
}

export type PredictionField = keyof PredictionFormValues;
export type FieldErrors = Partial<Record<PredictionField, string>>;

/** Empty form. The API's own defaults ("" and no tags) apply to the optional fields. */
export const EMPTY_FORM: PredictionFormValues = {
  title: '',
  description: '',
  tags: '',
  channel_title: '',
  category: '',
  country: '',
  duration_sec: '',
  channel_subscriber_count: '',
  channel_video_count: '',
  channel_view_count: '',
};

export function parseTags(text: string): string[] {
  return text
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Form values -> the exact PredictionRequest body (no extra fields). */
export function toPredictionRequest(values: PredictionFormValues): PredictionRequest {
  return {
    title: values.title,
    description: values.description,
    tags: parseTags(values.tags),
    channel_title: values.channel_title,
    category: values.category,
    country: values.country,
    duration_sec: Number(values.duration_sec),
    channel_subscriber_count: Number(values.channel_subscriber_count),
    channel_video_count: Number(values.channel_video_count),
    channel_view_count: Number(values.channel_view_count),
  };
}

function numberError(value: string, max: number, integer: boolean): string | undefined {
  if (value.trim() === '') return 'Required.';
  const n = Number(value);
  if (!Number.isFinite(n)) return 'Enter a number.';
  if (integer && !Number.isInteger(n)) return 'Enter a whole number.';
  if (n < 0) return 'Must be 0 or more.';
  if (n > max) return `Must be at most ${max.toLocaleString('en-US')}.`;
  return undefined;
}

/** Immediate client-side checks; returns an empty object when the form can be submitted. */
export function validatePrediction(values: PredictionFormValues): FieldErrors {
  const L = PREDICTION_LIMITS;
  const errors: FieldErrors = {};
  if (!values.title.trim()) errors.title = 'Required.';
  else if (values.title.length > L.title) errors.title = `At most ${L.title} characters.`;
  if (values.description.length > L.description) {
    errors.description = `At most ${L.description} characters.`;
  }
  if (values.channel_title.length > L.channel_title) {
    errors.channel_title = `At most ${L.channel_title} characters.`;
  }
  const tags = parseTags(values.tags);
  if (tags.length > L.tags) errors.tags = `At most ${L.tags} tags.`;
  else if (tags.some((t) => t.length > L.tag))
    errors.tags = `Each tag can have at most ${L.tag} characters.`;
  if (!values.category) errors.category = 'Select a category.';
  if (!values.country) errors.country = 'Select a country.';

  const numeric: [PredictionField, number, boolean][] = [
    ['duration_sec', L.duration_sec, false],
    ['channel_subscriber_count', L.channel_subscriber_count, true],
    ['channel_video_count', L.channel_video_count, true],
    ['channel_view_count', L.channel_view_count, true],
  ];
  for (const [field, max, integer] of numeric) {
    const error = numberError(values[field], max, integer);
    if (error) errors[field] = error;
  }
  return errors;
}

const FIELDS = new Set<string>(Object.keys(EMPTY_FORM));

/**
 * Maps backend 422 details ({field: "country"} or "tags.3") onto form fields.
 * Errors for fields the form does not know about are returned under `form`.
 */
export function mapServerErrors(details: { field?: string | null; message: string }[]): {
  fields: FieldErrors;
  form: string[];
} {
  const fields: FieldErrors = {};
  const form: string[] = [];
  for (const detail of details) {
    const name = detail.field?.split('.')[0] ?? '';
    if (FIELDS.has(name)) fields[name as PredictionField] ??= detail.message;
    else form.push(detail.message);
  }
  return { fields, form };
}
