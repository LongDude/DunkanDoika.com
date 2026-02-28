import type {
  SsoMessageResponse,
  SsoLoginRequest,
  SsoOauthProvider,
  SsoPasswordResetRequest,
  SsoRegisterRequest,
  SsoTokenResponse,
  SsoUser,
} from '../types/auth'
import type {
  BulkDeleteResponse,
  CreateForecastJobResponse,
  DatasetInfo,
  DatasetUploadResponse,
  ForecastJobInfo,
  ForecastResult,
  HistoryJobDetail,
  HistoryJobsPageResponse,
  ScenarioDetail,
  ScenarioInfo,
  ScenarioParams,
  UserPreset,
  UserPresetParams,
} from '../types/forecast'

const FORECAST_API = import.meta.env.VITE_API_BASE_URL ?? '/api'
const SSO_API = import.meta.env.VITE_SSO_API_BASE_URL ?? '/api'
const ACCESS_TOKEN_STORAGE_KEY = 'sso_access_token'

function resolveUrl(base: string, path = ''): URL {
  let cleanBase = base.trim().replace(/\/$/, '')
  if (!/^https?:\/\//i.test(cleanBase) && /^[a-z0-9.-]+\.[a-z]{2,}(\/.*)?$/i.test(cleanBase)) {
    cleanBase = `https://${cleanBase}`
  }
  if (/^https?:\/\//i.test(cleanBase)) {
    return new URL(`${cleanBase}${path}`)
  }
  return new URL(`${cleanBase}${path}`, window.location.origin)
}

function resolveForecastUrl(path = ''): URL {
  return resolveUrl(FORECAST_API, path)
}

function resolveSsoUrl(path = ''): URL {
  return resolveUrl(SSO_API, path)
}

export function getSsoOauthUrl(
  provider: SsoOauthProvider,
  redirectUrl = `${window.location.origin}${window.location.pathname}`,
): string {
  const url = resolveSsoUrl(`/oauth/${provider}`)
  url.searchParams.set('redirect_url', redirectUrl)
  return url.toString()
}

export function getForecastJobWsUrl(jobId: string): string {
  const apiUrl = resolveForecastUrl(`/ws/forecast/jobs/${jobId}`)
  const wsProtocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${apiUrl.host}${apiUrl.pathname}${apiUrl.search}`
}

async function extractErrorMessage(resp: Response): Promise<string> {
  let message = `${resp.status} ${resp.statusText}`
  try {
    const payload = await resp.json()
    const detail = payload?.detail
    if (typeof detail === 'string') {
      message = detail
    } else if (detail && typeof detail.message === 'string') {
      message = detail.message
    } else if (typeof payload?.error === 'string') {
      message = payload.error
    } else if (typeof payload?.message === 'string') {
      message = payload.message
    }
  } catch {
    const text = await resp.text()
    if (text) message = text
  }
  return message
}

async function unwrapJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    throw new Error(await extractErrorMessage(resp))
  }
  return resp.json() as Promise<T>
}

function readStoredAccessToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

function authHeader(required = false): Record<string, string> {
  const token = readStoredAccessToken()
  if (!token) {
    if (required) {
      throw new Error('Authorization token is missing')
    }
    return {}
  }
  return { Authorization: `Bearer ${token}` }
}

export async function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(resolveForecastUrl('/datasets/upload'), { method: 'POST', body: form })
  return unwrapJson<DatasetUploadResponse>(resp)
}

export async function getDatasetInfo(datasetId: string): Promise<DatasetInfo> {
  const resp = await fetch(resolveForecastUrl(`/datasets/${datasetId}`))
  return unwrapJson<DatasetInfo>(resp)
}

export async function createForecastJob(params: ScenarioParams): Promise<CreateForecastJobResponse> {
  const resp = await fetch(resolveForecastUrl('/forecast/jobs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(false) },
    body: JSON.stringify(params),
  })
  return unwrapJson<CreateForecastJobResponse>(resp)
}

export async function getForecastJob(jobId: string): Promise<ForecastJobInfo> {
  const resp = await fetch(resolveForecastUrl(`/forecast/jobs/${jobId}`))
  return unwrapJson<ForecastJobInfo>(resp)
}

export async function getForecastResult(jobId: string): Promise<ForecastResult> {
  const resp = await fetch(resolveForecastUrl(`/forecast/jobs/${jobId}/result`))
  return unwrapJson<ForecastResult>(resp)
}

export async function exportForecastCsvByJob(jobId: string): Promise<Blob> {
  const resp = await fetch(resolveForecastUrl(`/forecast/jobs/${jobId}/export/csv`))
  if (!resp.ok) throw new Error(await extractErrorMessage(resp))
  return resp.blob()
}

export async function exportForecastXlsxByJob(jobId: string): Promise<Blob> {
  const resp = await fetch(resolveForecastUrl(`/forecast/jobs/${jobId}/export/xlsx`))
  if (!resp.ok) throw new Error(await extractErrorMessage(resp))
  return resp.blob()
}

export async function saveScenario(name: string, params: ScenarioParams): Promise<ScenarioDetail> {
  const resp = await fetch(resolveForecastUrl('/scenarios'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, params }),
  })
  return unwrapJson<ScenarioDetail>(resp)
}

export async function listScenarios(): Promise<ScenarioInfo[]> {
  const resp = await fetch(resolveForecastUrl('/scenarios'))
  return unwrapJson<ScenarioInfo[]>(resp)
}

export async function loadScenario(id: string): Promise<ScenarioDetail> {
  const resp = await fetch(resolveForecastUrl(`/scenarios/${id}`))
  return unwrapJson<ScenarioDetail>(resp)
}

export async function runScenario(id: string): Promise<CreateForecastJobResponse> {
  const resp = await fetch(resolveForecastUrl(`/scenarios/${id}/run`), {
    method: 'POST',
    headers: { ...authHeader(false) },
  })
  return unwrapJson<CreateForecastJobResponse>(resp)
}

export async function listMyHistoryJobs(params?: {
  page?: number
  limit?: number
  status?: string
  q?: string
  date_from?: string
  date_to?: string
}): Promise<HistoryJobsPageResponse> {
  const url = resolveForecastUrl('/me/history/jobs')
  if (params) {
    if (params.page) url.searchParams.set('page', String(params.page))
    if (params.limit) url.searchParams.set('limit', String(params.limit))
    if (params.status) url.searchParams.set('status', params.status)
    if (params.q) url.searchParams.set('q', params.q)
    if (params.date_from) url.searchParams.set('date_from', params.date_from)
    if (params.date_to) url.searchParams.set('date_to', params.date_to)
  }
  const resp = await fetch(url, {
    headers: { ...authHeader(true) },
  })
  return unwrapJson<HistoryJobsPageResponse>(resp)
}

export async function getMyHistoryJob(jobId: string): Promise<HistoryJobDetail> {
  const resp = await fetch(resolveForecastUrl(`/me/history/jobs/${jobId}`), {
    headers: { ...authHeader(true) },
  })
  return unwrapJson<HistoryJobDetail>(resp)
}

export async function getMyHistoryJobResult(jobId: string): Promise<ForecastResult> {
  const resp = await fetch(resolveForecastUrl(`/me/history/jobs/${jobId}/result`), {
    headers: { ...authHeader(true) },
  })
  return unwrapJson<ForecastResult>(resp)
}

export async function deleteMyHistoryJob(jobId: string): Promise<BulkDeleteResponse> {
  const resp = await fetch(resolveForecastUrl(`/me/history/jobs/${jobId}`), {
    method: 'DELETE',
    headers: { ...authHeader(true) },
  })
  return unwrapJson<BulkDeleteResponse>(resp)
}

export async function bulkDeleteMyHistoryJobs(ids: string[]): Promise<BulkDeleteResponse> {
  const resp = await fetch(resolveForecastUrl('/me/history/jobs/bulk-delete'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(true) },
    body: JSON.stringify({ ids }),
  })
  return unwrapJson<BulkDeleteResponse>(resp)
}

export async function listMyPresets(): Promise<UserPreset[]> {
  const resp = await fetch(resolveForecastUrl('/me/presets'), {
    headers: { ...authHeader(true) },
  })
  return unwrapJson<UserPreset[]>(resp)
}

export async function createMyPreset(name: string, params: UserPresetParams): Promise<UserPreset> {
  const resp = await fetch(resolveForecastUrl('/me/presets'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(true) },
    body: JSON.stringify({ name, params }),
  })
  return unwrapJson<UserPreset>(resp)
}

export async function updateMyPreset(
  presetId: string,
  payload: { name?: string; params?: UserPresetParams },
): Promise<UserPreset> {
  const resp = await fetch(resolveForecastUrl(`/me/presets/${presetId}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeader(true) },
    body: JSON.stringify(payload),
  })
  return unwrapJson<UserPreset>(resp)
}

export async function deleteMyPreset(presetId: string): Promise<BulkDeleteResponse> {
  const resp = await fetch(resolveForecastUrl(`/me/presets/${presetId}`), {
    method: 'DELETE',
    headers: { ...authHeader(true) },
  })
  return unwrapJson<BulkDeleteResponse>(resp)
}

export async function bulkDeleteMyPresets(ids: string[]): Promise<BulkDeleteResponse> {
  const resp = await fetch(resolveForecastUrl('/me/presets/bulk-delete'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(true) },
    body: JSON.stringify({ ids }),
  })
  return unwrapJson<BulkDeleteResponse>(resp)
}

export async function ssoRegister(request: SsoRegisterRequest): Promise<SsoUser> {
  const resp = await fetch(resolveSsoUrl('/auth/create'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(request),
  })
  return unwrapJson<SsoUser>(resp)
}

export async function ssoLogin(request: SsoLoginRequest): Promise<SsoTokenResponse> {
  const resp = await fetch(resolveSsoUrl('/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(request),
  })
  return unwrapJson<SsoTokenResponse>(resp)
}

export async function ssoAuthenticate(accessToken: string): Promise<SsoUser> {
  const resp = await fetch(resolveSsoUrl('/auth/authenticate'), {
    method: 'GET',
    headers: { Authorization: `Bearer ${accessToken}` },
    credentials: 'include',
  })
  return unwrapJson<SsoUser>(resp)
}

export async function ssoRefresh(): Promise<SsoTokenResponse> {
  const resp = await fetch(resolveSsoUrl('/auth/refresh'), {
    method: 'POST',
    credentials: 'include',
  })
  return unwrapJson<SsoTokenResponse>(resp)
}

export async function ssoLogout(): Promise<void> {
  const resp = await fetch(resolveSsoUrl('/auth/logout'), {
    method: 'POST',
    credentials: 'include',
  })
  if (!resp.ok) {
    throw new Error(await extractErrorMessage(resp))
  }
}

export async function ssoRequestPasswordReset(request: SsoPasswordResetRequest): Promise<SsoMessageResponse> {
  const resp = await fetch(resolveSsoUrl('/auth/password-reset'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(request),
  })
  return unwrapJson<SsoMessageResponse>(resp)
}

export async function ssoConfirmPasswordReset(token: string): Promise<SsoMessageResponse> {
  const url = resolveSsoUrl('/auth/password-reset/confirm')
  url.searchParams.set('token', token)
  const resp = await fetch(url, {
    method: 'GET',
    credentials: 'include',
  })
  return unwrapJson<SsoMessageResponse>(resp)
}

export async function ssoConfirmEmail(token: string): Promise<void> {
  const url = resolveSsoUrl('/auth/confirm-email')
  url.searchParams.set('token', token)
  const resp = await fetch(url, {
    method: 'GET',
    credentials: 'include',
  })
  if (!resp.ok) {
    throw new Error(await extractErrorMessage(resp))
  }
}
