// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { ApiError, isApiError, isRetryableError, normalizeErrorResponse } from './errors';

const apiError = (status: number, code: string) =>
  new ApiError({ status, code, message: code, requestId: 'r' });

describe('isRetryableError', () => {
  it.each([
    [apiError(503, 'database_unavailable'), true],
    [apiError(503, 'database_busy'), true],
    [apiError(504, 'query_timeout'), true],
    [ApiError.network('r'), true],
    [ApiError.timeout(1000, 'r'), true],
    [apiError(422, 'invalid_filter'), false],
    [apiError(404, 'not_found'), false],
    [apiError(500, 'internal_error'), false],
    [apiError(413, 'payload_too_large'), false],
    [new Error('plain'), false],
    ['string', false],
  ])('%o -> %s', (error, expected) => {
    expect(isRetryableError(error)).toBe(expected);
  });
});

describe('ApiError', () => {
  it('is an Error with a stable name and defaults', () => {
    const error = apiError(422, 'invalid_parameter');
    expect(error).toBeInstanceOf(Error);
    expect(isApiError(error)).toBe(true);
    expect(error.name).toBe('ApiError');
    expect(error.field).toBeNull();
    expect(error.details).toEqual([]);
  });

  it('builds client-side timeout and network errors with status 0', () => {
    expect(ApiError.timeout(20000, 'r')).toMatchObject({ status: 0, code: 'timeout' });
    expect(ApiError.timeout(20000, 'r').message).toContain('20 seconds');
    expect(ApiError.network('r')).toMatchObject({ status: 0, code: 'network_error' });
  });
});

describe('normalizeErrorResponse', () => {
  it('ignores malformed envelopes', () => {
    const response = new Response(null, { status: 500 });
    const error = normalizeErrorResponse(response, { error: 'oops' }, 'sent');
    expect(error).toMatchObject({ status: 500, code: 'http_error', requestId: 'sent' });
  });

  it('prefers the body request id, then the header, then the sent id', () => {
    const withHeader = new Response(null, { status: 404, headers: { 'X-Request-ID': 'hdr' } });
    const envelope = (request_id: string | null) => ({
      error: { code: 'not_found', message: 'Not found', request_id },
    });
    expect(normalizeErrorResponse(withHeader, envelope('body'), 'sent').requestId).toBe('body');
    expect(normalizeErrorResponse(withHeader, envelope(null), 'sent').requestId).toBe('hdr');
    expect(
      normalizeErrorResponse(new Response(null, { status: 404 }), envelope(null), 'sent').requestId,
    ).toBe('sent');
  });
});
