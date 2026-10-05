import { describe, expect, it } from 'vitest';

import { resolveApiBaseUrl } from './config';

describe('resolveApiBaseUrl', () => {
  it('defaults to the local FastAPI server', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('http://localhost:8000');
    expect(resolveApiBaseUrl('  ')).toBe('http://localhost:8000');
  });

  it('strips trailing slashes', () => {
    expect(resolveApiBaseUrl('https://api.example.com/')).toBe('https://api.example.com');
  });

  it('treats "/" as the page origin (same-origin deployment behind the reverse proxy)', () => {
    expect(resolveApiBaseUrl('/', 'https://trending.example.com')).toBe(
      'https://trending.example.com',
    );
    expect(resolveApiBaseUrl(' / ', 'http://localhost:8080')).toBe('http://localhost:8080');
    expect(() => resolveApiBaseUrl('/', null)).toThrow(/page origin/);
  });

  it.each(['not a url', 'ftp://api.example.com', 'javascript:alert(1)'])('rejects %s', (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow(/VITE_API_BASE_URL/);
  });
});
