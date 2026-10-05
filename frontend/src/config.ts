const DEFAULT_API_BASE_URL = 'http://localhost:8000';

/**
 * Validates the configured API base URL (http/https only) and strips trailing slashes.
 *
 * `/` means "same origin as the page": the production container serves the app and proxies
 * /api to FastAPI on one origin, so the session cookie is first-party and no CORS is involved.
 * Unset keeps the development default (`npm run dev` against a local FastAPI on :8000).
 */
export function resolveApiBaseUrl(
  value: string | undefined,
  pageOrigin: string | null = globalThis.location?.origin ?? null,
): string {
  const trimmed = value?.trim();
  if (trimmed === '/') {
    if (!pageOrigin) throw new Error('VITE_API_BASE_URL=/ needs a browser page origin');
    return resolveApiBaseUrl(pageOrigin);
  }
  const raw = trimmed || DEFAULT_API_BASE_URL;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid URL: ${raw}`);
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(`VITE_API_BASE_URL must use http or https: ${raw}`);
  }
  return raw.replace(/\/+$/, '');
}

export const config = {
  apiBaseUrl: resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
} as const;
