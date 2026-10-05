import { useId, type ReactNode } from 'react';

import { Card, CardHeader } from '../ui/Card';

interface ChartCardProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Card for a chart or table: titled region (labelled by its heading) with a content area. */
export function ChartCard({ title, description, actions, children, className }: ChartCardProps) {
  const headingId = useId();
  return (
    <Card aria-labelledby={headingId} className={className}>
      <CardHeader id={headingId} title={title} description={description} actions={actions} />
      <div>{children}</div>
    </Card>
  );
}
