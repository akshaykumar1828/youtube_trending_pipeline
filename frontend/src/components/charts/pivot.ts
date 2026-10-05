/**
 * Reshapes API series into chart rows ({ date, [seriesKey]: value }). Pure reshaping for
 * Recharts — no values are computed or aggregated.
 */
export function pivotByDate<T extends { date: string }>(
  series: { key: string; points: T[] }[],
  value: (point: T) => number | null,
): Record<string, string | number | null>[] {
  const rows = new Map<string, Record<string, string | number | null>>();
  for (const s of series) {
    for (const point of s.points) {
      const row = rows.get(point.date) ?? { date: point.date };
      row[s.key] = value(point);
      rows.set(point.date, row);
    }
  }
  return [...rows.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}
