export type DatasetUploadResponse = {
  dataset_id: string
  n_rows: number
  report_date_suggested?: string | null
  status_counts: Record<string, number>
  quality_issues?: DatasetQualityIssue[]
}

export type DatasetInfo = DatasetUploadResponse & {
  original_filename: string
  created_at: string
}

export type DatasetQualityIssueSeverity = 'info' | 'warning' | 'error'
export type DatasetQualityIssue = {
  code: string
  severity: DatasetQualityIssueSeverity
  message: string
  row_count?: number
  sample_rows?: number[]
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

export type ScenarioMode = 'empirical' | 'theoretical'
export type PurchasePolicy = 'manual' | 'auto_counter' | 'auto_forecast'
export type SchemaVersion = 'legacy_v1' | 'herd_m5_v2'

export type ForecastResultMeta = {
  engine: 'herd_m5'
  mode: ScenarioMode
  purchase_policy: PurchasePolicy
  confidence_central: number
  assumptions: string[]
  warnings: string[]
  simulation_version: string
}

export type ForecastResult = {
  series_p50: ForecastSeries
  series_p10?: ForecastSeries | null
  series_p90?: ForecastSeries | null
  events: EventsByMonth[]
  future_point?: ForecastPoint | null
  meta?: ForecastResultMeta | null
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

export type HistoryJobItem = ForecastJobInfo & {
  has_result: boolean
}

export type HistoryJobDetail = HistoryJobItem & {
  params: ScenarioParams
}

export type HistoryJobsPageResponse = {
  items: HistoryJobItem[]
  total: number
  page: number
  limit: number
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

export type BulkDeleteSkipItem = {
  id: string
  reason: string
}

export type BulkDeleteResponse = {
  deleted_ids: string[]
  skipped: BulkDeleteSkipItem[]
}

export type PurchaseItem = {
  date_in: string
  count: number
  expected_calving_date?: string | null
  days_pregnant?: number | null
}

export type HerdM5ModelParams = {
  min_first_insem_age_days: number
  voluntary_waiting_period: number
  max_service_period_after_vwp: number
  population_regulation: number
  gestation_lo: number
  gestation_hi: number
  gestation_mu: number
  gestation_sigma: number
  heifer_birth_prob: number
  purchased_days_to_calving_lo: number
  purchased_days_to_calving_hi: number
}

export type ScenarioParams = {
  dataset_id: string
  report_date?: string | null
  horizon_months: number
  future_date?: string | null
  seed: number
  mc_runs: number
  mode: ScenarioMode
  purchase_policy: PurchasePolicy
  lead_time_days: number
  confidence_central: number
  model: HerdM5ModelParams
  purchases: PurchaseItem[]
}

export type ScenarioInfo = {
  scenario_id: string
  name: string
  created_at: string
  dataset_id: string
  report_date?: string | null
  horizon_months?: number | null
  schema_version: SchemaVersion
  is_legacy: boolean
  legacy_reason?: string | null
}

export type ScenarioDetail = {
  scenario_id: string
  name: string
  created_at: string
  schema_version: SchemaVersion
  is_legacy: boolean
  legacy_reason?: string | null
  params?: ScenarioParams | null
}

export type UserPresetParams = Omit<ScenarioParams, 'dataset_id'>

export type UserPreset = {
  preset_id: string
  owner_user_id: string
  name: string
  schema_version: SchemaVersion
  is_legacy: boolean
  legacy_reason?: string | null
  params?: UserPresetParams | null
  created_at: string
  updated_at: string
}

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
