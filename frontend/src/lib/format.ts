/**
 * Display formatting only. Values are shown exactly as the API returns them; nothing here
 * computes a metric.
 */

const EMPTY = '—';

const compactFormat = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
});
const integerFormat = new Intl.NumberFormat('en-US');
const dateFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
});
const shortDateFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});

type Num = number | null | undefined;

/** 1234567 -> "1.2M" */
export function formatCompact(value: Num): string {
  return value == null ? EMPTY : compactFormat.format(value);
}

/** 1234567 -> "1,234,567" */
export function formatInteger(value: Num): string {
  return value == null ? EMPTY : integerFormat.format(value);
}

/** A ratio from the API (0.0296) shown as a percentage: "2.96%". */
export function formatRate(rate: Num, digits = 2): string {
  return rate == null ? EMPTY : `${(rate * 100).toFixed(digits)}%`;
}

/** A value the API already expresses in percent (53.79) -> "53.8%". */
export function formatPercent(value: Num, digits = 1): string {
  return value == null ? EMPTY : `${value.toFixed(digits)}%`;
}

function signed(value: number, digits: number): string {
  const fixed = value.toFixed(digits);
  return value > 0 ? `+${fixed}` : fixed;
}

/** API change_pct -> "+5.3%" / "-0.2%"; null when no comparison is available. */
export function formatChangePct(value: Num): string | null {
  return value == null ? null : `${signed(value, 1)}%`;
}

/** API change_pts (percentage points) -> "+0.16 pp". */
export function formatChangePts(value: Num): string | null {
  return value == null ? null : `${signed(value, 2)} pp`;
}

function toUtcDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

/** "2025-12-07" or "2025-12-09T09:33:03" -> "Dec 7, 2025" (no time-zone shift). */
export function formatDate(value: string | null | undefined): string {
  const date = value ? toUtcDate(value) : null;
  return date ? dateFormat.format(date) : EMPTY;
}

/** "2025-12-07" -> "Dec 7" (chart axes). */
export function formatShortDate(value: string | null | undefined): string {
  const date = value ? toUtcDate(value) : null;
  return date ? shortDateFormat.format(date) : EMPTY;
}

/** 3723 -> "1:02:03", 229 -> "3:49". */
export function formatDuration(seconds: Num): string {
  if (seconds == null) return EMPTY;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}
