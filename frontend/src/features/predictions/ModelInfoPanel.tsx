import type { ModelInfo } from '../../api/types';
import { Badge } from '../../components/ui/Badge';

/** The model card exactly as returned by /api/v1/predictions/model-info. */
export function ModelInfoPanel({ info }: { info: ModelInfo }) {
  const metricEntries = Object.entries(info.reported_metrics).filter(([key]) => key !== 'note');
  return (
    <div className="grid gap-6 p-4 lg:grid-cols-2">
      <div className="space-y-4 text-sm text-slate-700">
        <div>
          <h3 className="text-xs font-semibold text-slate-900">What the model predicts</h3>
          <p className="mt-1">{info.label_definition}</p>
          <p className="mt-2 text-slate-600">{info.not_a_prediction_of}</p>
        </div>
        <div>
          <h3 className="text-xs font-semibold text-slate-900">Training data</h3>
          <p className="mt-1">{info.training_data}</p>
        </div>
        <div>
          <h3 className="text-xs font-semibold text-slate-900">Reported performance</h3>
          <dl className="mt-1 space-y-0.5">
            {metricEntries.map(([key, value]) => (
              <div key={key} className="flex gap-2">
                <dt className="font-medium uppercase">{key.replace(/_/g, '-')}</dt>
                <dd className="tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          {info.reported_metrics.note && (
            <p className="mt-1 text-xs text-slate-500">{info.reported_metrics.note}</p>
          )}
        </div>
      </div>
      <div className="space-y-4 text-sm text-slate-700">
        <div>
          <h3 className="text-xs font-semibold text-slate-900">Supported inputs</h3>
          <p className="mt-1 text-xs text-slate-500">{info.category_input}</p>
          <ul aria-label="Supported countries" className="mt-2 flex flex-wrap gap-1">
            {info.supported_countries.map((c) => (
              <li key={c}>
                <Badge className="font-mono">{c}</Badge>
              </li>
            ))}
          </ul>
          <ul aria-label="Supported categories" className="mt-2 flex flex-wrap gap-1">
            {info.supported_categories.map((c) => (
              <li key={c}>
                <Badge>{c}</Badge>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs font-semibold text-slate-900">Limitations</h3>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-slate-600">
            {info.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-500">
          {info.name} · version <span className="font-mono">{info.version}</span>
        </p>
      </div>
    </div>
  );
}
