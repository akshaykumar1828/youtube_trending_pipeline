/**
 * Downloads the FastAPI OpenAPI contract into frontend/openapi.json (the source for type generation).
 *
 * Usage: npm run api:snapshot   (backend running in development mode, where /openapi.json is enabled)
 * Base URL: VITE_API_BASE_URL from the environment or frontend/.env, default http://localhost:8000.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function baseUrlFromDotEnv() {
  try {
    const line = readFileSync(resolve(root, '.env'), 'utf8')
      .split(/\r?\n/)
      .find((l) => l.startsWith('VITE_API_BASE_URL='));
    return line?.slice('VITE_API_BASE_URL='.length).trim() || undefined;
  } catch {
    return undefined;
  }
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((k) => [k, sortKeys(value[k])]),
    );
  }
  return value;
}

const baseUrl = (
  process.env.VITE_API_BASE_URL ||
  baseUrlFromDotEnv() ||
  'http://localhost:8000'
).replace(/\/+$/, '');
const url = `${baseUrl}/openapi.json`;

const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
if (!response.ok) {
  console.error(`Failed to download ${url}: HTTP ${response.status}`);
  process.exit(1);
}
const spec = await response.json();
if (!spec.openapi || !spec.paths) {
  console.error(`${url} did not return an OpenAPI document`);
  process.exit(1);
}

const target = resolve(root, 'openapi.json');
writeFileSync(target, JSON.stringify(sortKeys(spec), null, 2) + '\n');
console.log(
  `Saved ${Object.keys(spec.paths).length} paths / ${Object.keys(spec.components?.schemas ?? {}).length} schemas from ${url}`,
);
