/**
 * Readable aliases over the generated OpenAPI types. Nothing here re-declares a backend
 * shape: every type is derived from src/api/generated/schema.ts (regenerate with `npm run api:types`).
 */
import type { components, paths } from './generated/schema';

type Schemas = components['schemas'];

// ---- helpers derived from the contract ----
type JsonOf<R> = R extends { content: { 'application/json': infer T } } ? T : never;
type Operation<P extends keyof paths, M extends 'get' | 'post'> = NonNullable<paths[P][M]>;

/** Success (200) JSON body of an endpoint, including its {filters, data} / {data} envelope. */
export type ApiResponse<P extends keyof paths, M extends 'get' | 'post' = 'get'> =
  Operation<P, M> extends { responses: { 200: infer R } } ? JsonOf<R> : never;

/** Query parameters of an endpoint. */
export type QueryParams<P extends keyof paths, M extends 'get' | 'post' = 'get'> = NonNullable<
  Operation<P, M> extends { parameters: { query?: infer Q } } ? Q : never
>;

/** The four global filter parameters shared by every filtered endpoint. */
export type FilterParams = Pick<
  QueryParams<'/api/v1/overview/kpis'>,
  'start_date' | 'end_date' | 'country' | 'category'
>;

/** Endpoint-specific (non-filter) query parameters. */
export type DailyVolumeParams = Omit<
  QueryParams<'/api/v1/overview/daily-volume'>,
  keyof FilterParams
>;
export type EngagementParams = Omit<
  QueryParams<'/api/v1/analytics/engagement'>,
  keyof FilterParams
>;
export type ChannelParams = Omit<QueryParams<'/api/v1/analytics/channels'>, keyof FilterParams>;
export type VideoListParams = Omit<QueryParams<'/api/v1/videos'>, keyof FilterParams>;

// ---- schema aliases ----
export type AppliedFilters = Schemas['AppliedFilters'];
export type FilterOptions = Schemas['FilterOptions'];
export type CountryOption = Schemas['CountryOption'];

export type Kpis = Schemas['Kpis'];
export type CountMetric = Schemas['CountMetric'];
export type RateMetric = Schemas['RateMetric'];
export type DailyVolume = Schemas['DailyVolume'];
export type DailySeries = Schemas['DailySeries'];
export type DailyPoint = Schemas['DailyPoint'];

export type CategoryPerformance = Schemas['CategoryPerformance'];
export type CountryPerformance = Schemas['CountryPerformance'];
export type EngagementAnalysis = Schemas['EngagementAnalysis'];
export type ChannelPerformance = Schemas['ChannelPerformance'];

export type VideoPage = Schemas['VideoPage'];
export type VideoListItem = Schemas['VideoListItem'];
export type VideoDetail = Schemas['VideoDetail'];
export type HistoryPoint = Schemas['HistoryPoint'];

export type PredictionRequest = Schemas['PredictionRequest'];
export type Prediction = Schemas['Prediction'];
export type ModelInfo = Schemas['ModelInfo'];

export type ErrorResponse = Schemas['ErrorResponse'];

export type CurrentUser = Schemas['CurrentUser'];
export type RegisterRequest = Schemas['RegisterRequest'];
export type LoginRequest = Schemas['LoginRequest'];
export type TenantDetail = Schemas['TenantDetail'];
export type Member = Schemas['Member'];
export type CreateMemberRequest = Schemas['CreateMemberRequest'];
export type UpdateMemberRequest = Schemas['UpdateMemberRequest'];
export type Role = Schemas['Role'];
export type Permission = Schemas['Permission'];

// ---- enums (string unions generated from the backend whitelists) ----
export type VideoSort = Schemas['VideoSort'];
export type SortOrder = Schemas['SortOrder'];
export type ChannelSort = Schemas['ChannelSort'];
export type DailySplit = Schemas['DailySplit'];
