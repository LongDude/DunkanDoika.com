export type DatasetUploadResponse = {
  dataset_id: string
  n_rows: number
  report_date_suggested?: string | null
  status_counts: Record<string, number>
}

export type DatasetQualityIssueSeverity = 'info' | 'warning' | 'error'
export type DatasetQualityIssue = {
  code: string
  severity: DatasetQualityIssueSeverity
  message: string
}

export type ForecastPoint = {
  date: string
  milking_count: number
  dry_count: number
  heifer_count: number
  pregnant_heifer_count: number
  avg_days_in_milk: number | null
}

export type ForecastSeries = { points: ForecastPoint[] }

export type EventsByMonth = {
  month: string
  calvings: number
  dryoffs: number
  culls: number
  purchases_in: number
  heifer_intros: number
}

export type ForecastResult = {
  series_p50: ForecastSeries
  series_p10?: ForecastSeries | null
  series_p90?: ForecastSeries | null
  events: EventsByMonth[]
  future_point?: ForecastPoint | null
}

export type ForecastJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'

export type ForecastJobInfo = {
  job_id: string
  dataset_id: string
  scenario_id?: string | null
  status: ForecastJobStatus
  progress_pct: number
  completed_runs: number
  total_runs: number
  error_message?: string | null
  queued_at: string
  started_at?: string | null
  finished_at?: string | null
  expires_at?: string | null
}

export type ForecastJobWsEventType = 'job_progress' | 'job_succeeded' | 'job_failed' | 'heartbeat'

export type ForecastJobWsEvent = {
  type: ForecastJobWsEventType
  job_id: string
  status?: ForecastJobStatus
  progress_pct?: number
  completed_runs?: number
  total_runs?: number
  partial_result?: ForecastResult | null
  error_message?: string | null
  ts: string
}

export type CreateForecastJobResponse = {
  job: ForecastJobInfo
}

export type PurchaseItem = {
  date_in: string
  count: number
  expected_calving_date?: string | null
  days_pregnant?: number | null
}

export type ServicePeriodParams = {
  mean_days: number
  std_days: number
  min_days_after_calving: number
}

export type HeiferInsemParams = {
  min_age_days: number
  max_age_days: number
}

export type ScenarioInfo = {
  scenario_id: string
  name: string
  created_at: string
  dataset_id: string
  report_date: string
  horizon_months: number
}

export type CullingParams = {
  estimate_from_dataset: boolean
  grouping: CullGrouping
  fallback_monthly_hazard: number
  age_band_years: number
}

export type ReplacementParams = {
  enabled: boolean
  annual_heifer_ratio: number
  lookahead_months: number
}

export type ScenarioParams = {
  dataset_id: string
  report_date: string
  horizon_months: number
  future_date?: string | null
  seed: number
  mc_runs: number
  service_period: ServicePeriodParams
  heifer_insem: HeiferInsemParams
  culling: CullingParams
  replacement: ReplacementParams
  purchases: PurchaseItem[]
}

export type ScenarioDetail = {
  scenario_id: string
  name: string
  created_at: string
  params: ScenarioParams
}

export type CullGrouping = 'lactation' | 'lactation_status' | 'age_band'
export type ScenarioPreset = 'baseline' | 'conservative' | 'aggressive'

export type UiValidationIssue = {
  field: string
  message: string
  severity: DatasetQualityIssueSeverity
}

export type DisabledReason = {
  disabled: boolean
  reason: string | null
}

export type CompareItem = {
  id: string
  label: string
  res: ForecastResult
}

export type ComparisonDeltaRow = {
  id: string
  label: string
  dim_delta: number | null
  milking_delta: number
  dry_delta: number
  heifer_delta: number
  pregnant_heifer_delta: number
}

export type ForecastKpiSnapshot = {
  date: string
  p50_dim: number | null
  milking_count: number
  dry_ratio: number | null
  trend_delta: number | null
}
