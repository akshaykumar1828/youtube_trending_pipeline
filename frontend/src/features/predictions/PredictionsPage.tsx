import { Info } from 'lucide-react';
import { useMemo, useState } from 'react';

import { isApiError } from '../../api/errors';
import type { PredictionRequest } from '../../api/types';
import { ChartCard } from '../../components/data/ChartCard';
import { ErrorState, LoadingState } from '../../components/data/states';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { PageHeader } from '../../layouts/PageHeader';
import { useFilterOptions } from '../filters/useFilterOptions';
import { isValidationError, mapServerErrors } from './form';
import { ModelInfoPanel } from './ModelInfoPanel';
import { PredictionForm } from './PredictionForm';
import { PredictionResult } from './PredictionResult';
import { useModelInfo, usePrediction } from './queries';

export const DISCLAIMER =
  'This model estimates high-performance probability for videos that are already represented in the trending dataset. It does not predict whether an arbitrary video will enter YouTube Trending.';

export function PredictionsPage() {
  const modelInfo = useModelInfo();
  const options = useFilterOptions(); // only for country display names (shared cache)
  const prediction = usePrediction();
  const [lastRequest, setLastRequest] = useState<PredictionRequest | null>(null);

  const countryNames = useMemo(
    () => Object.fromEntries((options.data?.countries ?? []).map((c) => [c.code, c.name])),
    [options.data],
  );

  const serverErrors = useMemo(() => {
    const error = prediction.error;
    if (!isValidationError(error)) return { fields: {}, form: [] };
    const details =
      error.details.length > 0 ? error.details : [{ field: error.field, message: error.message }];
    return mapServerErrors(details);
  }, [prediction.error]);

  const submit = (request: PredictionRequest) => {
    setLastRequest(request);
    prediction.mutate(request);
  };

  const modelUnavailable =
    isApiError(modelInfo.error) && modelInfo.error.code === 'model_unavailable';

  return (
    <>
      <PageHeader
        title="ML predictions"
        description="Score how likely a trending video is to be a high performer, using the frozen model served by the API."
      />
      <p className="flex items-start gap-2 rounded-md border border-accent-200 bg-accent-50 px-3 py-2.5 text-sm text-slate-700">
        <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-accent-600" />
        <span>{DISCLAIMER}</span>
      </p>

      {modelInfo.isPending ? (
        <Card>
          <LoadingState rows={8} label="Loading model information" />
        </Card>
      ) : modelInfo.isError ? (
        <Card>
          {modelUnavailable ? (
            <div role="alert" className="px-6 py-10 text-center">
              <p className="text-sm font-medium text-slate-800">
                The prediction model is unavailable
              </p>
              <p className="mt-1 text-xs text-slate-600">
                The model is disabled or failed to load on the server. The rest of the dashboard
                keeps working.
              </p>
              <Button size="sm" className="mt-3" onClick={() => void modelInfo.refetch()}>
                Check again
              </Button>
            </div>
          ) : (
            <ErrorState error={modelInfo.error} onRetry={() => void modelInfo.refetch()} />
          )}
        </Card>
      ) : (
        <>
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
            <ChartCard
              title="Video and channel"
              description="The inputs accepted by the prediction API."
            >
              <PredictionForm
                modelInfo={modelInfo.data}
                countryNames={countryNames}
                serverErrors={serverErrors.fields}
                isSubmitting={prediction.isPending}
                onSubmit={submit}
              />
            </ChartCard>
            <ChartCard title="Result" className="lg:sticky lg:top-20">
              <div aria-live="polite">
                <PredictionResult
                  status={prediction.status}
                  data={prediction.data?.data}
                  error={prediction.error}
                  formErrors={serverErrors.form}
                  componentDescriptions={modelInfo.data.components}
                  countryNames={countryNames}
                  onRetry={() => lastRequest && prediction.mutate(lastRequest)}
                />
              </div>
            </ChartCard>
          </div>
          <ChartCard title="About the model" description="Model card returned by the API.">
            <ModelInfoPanel info={modelInfo.data} />
          </ChartCard>
        </>
      )}
    </>
  );
}
