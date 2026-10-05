// @vitest-environment node
import { describe, expect, it } from 'vitest';

import {
  formatChangePct,
  formatChangePts,
  formatCompact,
  formatDate,
  formatDuration,
  formatInteger,
  formatPercent,
  formatRate,
  formatShortDate,
} from './format';

describe('format', () => {
  it('formats numbers', () => {
    expect(formatCompact(6493963164)).toBe('6.5B');
    expect(formatCompact(null)).toBe('—');
    expect(formatInteger(53668)).toBe('53,668');
  });

  it('shows API ratios as percentages and API percents as-is', () => {
    expect(formatRate(0.02955)).toBe('2.96%');
    expect(formatPercent(53.79)).toBe('53.8%');
  });

  it('formats changes with explicit signs; engagement in percentage points', () => {
    expect(formatChangePct(5.27)).toBe('+5.3%');
    expect(formatChangePct(-0.6)).toBe('-0.6%');
    expect(formatChangePct(null)).toBeNull();
    expect(formatChangePts(0.1592)).toBe('+0.16 pp');
  });

  it('formats dates without time-zone shifts', () => {
    expect(formatDate('2025-12-07')).toBe('Dec 7, 2025');
    expect(formatDate('2025-12-09T23:59:59')).toBe('Dec 9, 2025');
    expect(formatShortDate('2026-01-05')).toBe('Jan 5');
    expect(formatDate(null)).toBe('—');
  });

  it('formats durations', () => {
    expect(formatDuration(229)).toBe('3:49');
    expect(formatDuration(3723)).toBe('1:02:03');
    expect(formatDuration(0)).toBe('0:00');
  });
});
