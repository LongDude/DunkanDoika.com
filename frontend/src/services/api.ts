import type {
  DatasetUploadResponse,
  ForecastResult,
  ScenarioDetail,
  ScenarioInfo,
  ScenarioParams,
} from '../types/forecast'

const API = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function unwrapJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const message = await resp.text()
    throw new Error(message || `${resp.status} ${resp.statusText}`)
  }
  return resp.json() as Promise<T>
}

export async function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${API}/datasets/upload`, { method: 'POST', body: form })
  return unwrapJson<DatasetUploadResponse>(resp)
}

export async function runForecast(params: ScenarioParams): Promise<ForecastResult> {
  const resp = await fetch(`${API}/forecast/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  return unwrapJson<ForecastResult>(resp)
}

export async function exportForecastCsv(params: ScenarioParams): Promise<Blob> {
  const resp = await fetch(`${API}/forecast/export/csv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!resp.ok) throw new Error(await resp.text())
  return resp.blob()
}

export async function exportForecastXlsx(params: ScenarioParams): Promise<Blob> {
  const resp = await fetch(`${API}/forecast/export/xlsx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!resp.ok) throw new Error(await resp.text())
  return resp.blob()
}

export async function saveScenario(name: string, params: ScenarioParams): Promise<ScenarioDetail> {
  const resp = await fetch(`${API}/scenarios`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, params }),
  })
  return unwrapJson<ScenarioDetail>(resp)
}

export async function listScenarios(): Promise<ScenarioInfo[]> {
  const resp = await fetch(`${API}/scenarios`)
  return unwrapJson<ScenarioInfo[]>(resp)
}

export async function loadScenario(id: string): Promise<ScenarioDetail> {
  const resp = await fetch(`${API}/scenarios/${id}`)
  return unwrapJson<ScenarioDetail>(resp)
}

export async function runScenario(id: string): Promise<ForecastResult> {
  const resp = await fetch(`${API}/scenarios/${id}/run`, { method: 'POST' })
  return unwrapJson<ForecastResult>(resp)
}
