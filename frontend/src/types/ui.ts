export type RouteScreenId = 'dataset' | 'scenarios' | 'forecast' | 'comparison' | 'history' | 'export'

export type UiActionState = 'idle' | 'loading' | 'success' | 'error'
export type UiNoticeLevel = 'info' | 'success' | 'warning' | 'error'

export type UiNotice = {
  id: string
  level: UiNoticeLevel
  message: string
  ttlMs?: number
}

export type ChartViewState = {
  showP10: boolean
  showP50: boolean
  showP90: boolean
  herdMode: 'line' | 'stacked'
}
