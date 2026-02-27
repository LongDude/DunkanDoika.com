import type {
  CreateForecastJobResponse,
  DatasetUploadResponse,
  ForecastJobInfo,
  ForecastResult,
  ScenarioDetail,
  ScenarioInfo,
  ScenarioParams,
} from '../types/forecast'

const API = import.meta.env.VITE_API_BASE_URL ?? '/api'

function resolveApiUrl(path = ''): URL {
  return new URL(`${API.replace(/\/$/, '')}${path}`, window.location.origin)
}

export function getForecastJobWsUrl(jobId: string): string {
  const apiUrl = resolveApiUrl(`/ws/forecast/jobs/${jobId}`)
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

export async function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(resolveApiUrl('/datasets/upload'), { method: 'POST', body: form })
  return unwrapJson<DatasetUploadResponse>(resp)
}

export async function createForecastJob(params: ScenarioParams): Promise<CreateForecastJobResponse> {
  const resp = await fetch(resolveApiUrl('/forecast/jobs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  return unwrapJson<CreateForecastJobResponse>(resp)
}

export async function getForecastJob(jobId: string): Promise<ForecastJobInfo> {
  const resp = await fetch(resolveApiUrl(`/forecast/jobs/${jobId}`))
  return unwrapJson<ForecastJobInfo>(resp)
}

export async function getForecastResult(jobId: string): Promise<ForecastResult> {
  const resp = await fetch(resolveApiUrl(`/forecast/jobs/${jobId}/result`))
  return unwrapJson<ForecastResult>(resp)
}

export async function exportForecastCsvByJob(jobId: string): Promise<Blob> {
  const resp = await fetch(resolveApiUrl(`/forecast/jobs/${jobId}/export/csv`))
  if (!resp.ok) throw new Error(await extractErrorMessage(resp))
  return resp.blob()
}

export async function exportForecastXlsxByJob(jobId: string): Promise<Blob> {
  const resp = await fetch(resolveApiUrl(`/forecast/jobs/${jobId}/export/xlsx`))
  if (!resp.ok) throw new Error(await extractErrorMessage(resp))
  return resp.blob()
}

export async function saveScenario(name: string, params: ScenarioParams): Promise<ScenarioDetail> {
  const resp = await fetch(resolveApiUrl('/scenarios'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, params }),
  })
  return unwrapJson<ScenarioDetail>(resp)
}

export async function listScenarios(): Promise<ScenarioInfo[]> {
  const resp = await fetch(resolveApiUrl('/scenarios'))
  return unwrapJson<ScenarioInfo[]>(resp)
}

export async function loadScenario(id: string): Promise<ScenarioDetail> {
  const resp = await fetch(resolveApiUrl(`/scenarios/${id}`))
  return unwrapJson<ScenarioDetail>(resp)
}

export async function runScenario(id: string): Promise<CreateForecastJobResponse> {
  const resp = await fetch(resolveApiUrl(`/scenarios/${id}/run`), { method: 'POST' })
  return unwrapJson<CreateForecastJobResponse>(resp)
}
