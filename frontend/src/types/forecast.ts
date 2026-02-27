export type DatasetUploadResponse = {
  dataset_id: string
  n_rows: number
  report_date_suggested?: string | null
  status_counts: Record<string, number>
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

export type PurchaseItem = {
  date_in: string
  count: number
  expected_calving_date?: string | null
  days_pregnant?: number | null
}

export type ScenarioInfo = {
  scenario_id: string
  name: string
  created_at: string
  dataset_id: string
  report_date: string
  horizon_months: number
}

export type ScenarioDetail = {
  scenario_id: string
  name: string
  created_at: string
  params: any
}

export type CullGrouping = 'lactation' | 'lactation_status' | 'age_band'

export type CompareItem = {
  id: string
  label: string
  res: ForecastResult
}
