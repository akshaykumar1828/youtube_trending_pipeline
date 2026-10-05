import type { components } from './generated/schema';

type ErrorBody = components['schemas']['ErrorBody'];
type ErrorDetail = components['schemas']['ErrorDetail'];

export const REQUEST_ID_HEADER = 'X-Request-ID';

/** Codes produced by the client itself; all other codes come from the backend error envelope. */
export type ClientErrorCode = 'network_error' | 'timeout' | 'invalid_response' | 'http_error';

/**
 * The single error type thrown by the API layer.
 * `status` is 0 when no HTTP response was received (network failure or timeout).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;
  readonly details: ErrorDetail[];
  readonly requestId: string | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    requestId: string | null;
    field?: string | null;
    details?: ErrorDetail[] | null;
    cause?: unknown;
  }) {
    super(init.message, { cause: init.cause });
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.field = init.field ?? null;
    this.details = init.details ?? [];
    this.requestId = init.requestId;
  }

  static timeout(timeoutMs: number, requestId: string, cause?: unknown): ApiError {
    return new ApiError({
      status: 0,
      code: 'timeout',
      message: `The request did not complete within ${timeoutMs / 1000} seconds.`,
      requestId,
      cause,
    });
  }

  static network(requestId: string, cause?: unknown): ApiError {
    return new ApiError({
      status: 0,
      code: 'network_error',
      message: 'The API could not be reached.',
      requestId,
      cause,
    });
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

function isErrorEnvelope(body: unknown): body is { error: ErrorBody } {
  if (typeof body !== 'object' || body === null || !('error' in body)) return false;
  const error = (body as { error: unknown }).error;
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as ErrorBody).code === 'string' &&
    typeof (error as ErrorBody).message === 'string'
  );
}

/**
 * Converts a non-successful (or empty successful) response into an ApiError.
 * Uses the backend envelope {"error": {code, message, field, request_id, details}} when present;
 * otherwise falls back to a generic `http_error`. The request id prefers the backend's value,
 * then the X-Request-ID response header, then the id this client sent.
 */
export function normalizeErrorResponse(
  response: Response,
  body: unknown,
  sentRequestId: string,
): ApiError {
  const headerId = response.headers.get(REQUEST_ID_HEADER);

  if (response.ok) {
    return new ApiError({
      status: response.status,
      code: 'invalid_response',
      message: 'The API returned an empty or invalid response.',
      requestId: headerId ?? sentRequestId,
    });
  }

  if (isErrorEnvelope(body)) {
    const e = body.error;
    return new ApiError({
      status: response.status,
      code: e.code,
      message: e.message,
      field: e.field ?? null,
      details: e.details ?? [],
      requestId: e.request_id ?? headerId ?? sentRequestId,
    });
  }

  return new ApiError({
    status: response.status,
    code: 'http_error',
    message: `Request failed with HTTP ${response.status}.`,
    requestId: headerId ?? sentRequestId,
  });
}

/** Transient failures worth one retry: service unavailable, gateway timeout, network, timeout. */
export function isRetryableError(error: unknown): boolean {
  if (!isApiError(error)) return false;
  return (
    error.status === 503 ||
    error.status === 504 ||
    error.code === 'network_error' ||
    error.code === 'timeout'
  );
}
