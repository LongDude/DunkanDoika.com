import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createForecastJob,
  exportForecastCsvByJob,
  exportForecastXlsxByJob,
  getForecastJob,
  getForecastJobWsUrl,
  getForecastResult,
  runScenario,
} from '../services/api'
import type {
  ForecastJobInfo,
  ForecastJobWsEvent,
  ForecastResult,
  ScenarioParams,
} from '../types/forecast'

type RunStatus = 'idle' | 'queued' | 'running' | 'success' | 'error'
type TransportMode = 'idle' | 'ws' | 'polling'

const JOB_POLL_INTERVAL_MS = 1000
const JOB_POLL_MAX_ATTEMPTS = 600

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function useForecastRun() {
  const { t } = useI18n()

  const status = ref<RunStatus>('idle')
  const running = computed(() => status.value === 'queued' || status.value === 'running')
  const result = ref<ForecastResult | null>(null)
  const lastSuccessfulResult = ref<ForecastResult | null>(null)
  const currentJob = ref<ForecastJobInfo | null>(null)
  const lastSuccessfulJob = ref<ForecastJobInfo | null>(null)
  const currentProgress = computed(() => currentJob.value?.progress_pct ?? 0)
  const completedRuns = computed(() => currentJob.value?.completed_runs ?? 0)
  const totalRuns = computed(() => currentJob.value?.total_runs ?? 0)
  const lastRunAt = ref<string | null>(null)
  const lastError = ref<string | null>(null)
  const transportMode = ref<TransportMode>('idle')
  const activePollToken = ref(0)
  const liveSocket = ref<WebSocket | null>(null)

  function closeLiveSocket() {
    if (!liveSocket.value) return
    liveSocket.value.onopen = null
    liveSocket.value.onmessage = null
    liveSocket.value.onerror = null
    liveSocket.value.onclose = null
    if (
      liveSocket.value.readyState === WebSocket.OPEN ||
      liveSocket.value.readyState === WebSocket.CONNECTING
    ) {
      liveSocket.value.close()
    }
    liveSocket.value = null
  }

  function mergeCurrentJob(jobPatch: Partial<ForecastJobInfo>) {
    if (!currentJob.value) return
    currentJob.value = { ...currentJob.value, ...jobPatch } as ForecastJobInfo
  }

  function applyLiveEvent(event: ForecastJobWsEvent) {
    if (event.status === 'queued') {
      status.value = 'queued'
    } else if (event.status === 'running') {
      status.value = 'running'
    }

    mergeCurrentJob({
      status: event.status,
      progress_pct: event.progress_pct,
      completed_runs: event.completed_runs,
      total_runs: event.total_runs,
      error_message: event.error_message,
    })

    if (event.partial_result) {
      result.value = event.partial_result
    }
  }

  async function finalizeSuccess(jobId: string, event: ForecastJobWsEvent | null = null) {
    let finalJob = currentJob.value
    try {
      finalJob = await getForecastJob(jobId)
      currentJob.value = finalJob
    } catch {
      // keep last known job snapshot if network call failed
    }

    const finalResult = event?.partial_result ?? (await getForecastResult(jobId))
    result.value = finalResult
    lastSuccessfulResult.value = finalResult
    if (finalJob) {
      lastSuccessfulJob.value = finalJob
      lastRunAt.value = finalJob.finished_at ?? new Date().toISOString()
    } else {
      lastRunAt.value = new Date().toISOString()
    }
    status.value = 'success'
    transportMode.value = 'idle'
    closeLiveSocket()
    return finalResult
  }

  async function pollJobUntilDone(jobId: string, token: number, failedFallbackMessage: string) {
    transportMode.value = 'polling'
    for (let attempt = 0; attempt < JOB_POLL_MAX_ATTEMPTS; attempt += 1) {
      if (token !== activePollToken.value) return null

      const job = await getForecastJob(jobId)
      currentJob.value = job

      if (job.status === 'queued') {
        status.value = 'queued'
      } else if (job.status === 'running') {
        status.value = 'running'
      } else if (job.status === 'succeeded') {
        return await finalizeSuccess(jobId)
      } else {
        status.value = 'error'
        lastError.value = job.error_message || failedFallbackMessage
        transportMode.value = 'idle'
        throw new Error(lastError.value)
      }

      await sleep(JOB_POLL_INTERVAL_MS)
    }

    status.value = 'error'
    lastError.value = t('alerts.jobTimeout')
    transportMode.value = 'idle'
    throw new Error(lastError.value)
  }

  async function consumeJobViaWs(jobId: string, token: number, failedFallbackMessage: string): Promise<boolean> {
    if (typeof WebSocket === 'undefined') return false

    return new Promise<boolean>((resolve, reject) => {
      let settled = false
      const ws = new WebSocket(getForecastJobWsUrl(jobId))
      liveSocket.value = ws

      const fallback = () => {
        if (settled) return
        settled = true
        transportMode.value = 'polling'
        closeLiveSocket()
        resolve(false)
      }

      ws.onopen = () => {
        if (token !== activePollToken.value) {
          settled = true
          closeLiveSocket()
          resolve(true)
          return
        }
        transportMode.value = 'ws'
      }

      ws.onmessage = async message => {
        if (settled || token !== activePollToken.value) return
        let event: ForecastJobWsEvent
        try {
          event = JSON.parse(message.data) as ForecastJobWsEvent
        } catch {
          return
        }

        if (event.type === 'heartbeat') return

        applyLiveEvent(event)

        if (event.type === 'job_succeeded') {
          try {
            settled = true
            await finalizeSuccess(jobId, event)
            resolve(true)
          } catch (err) {
            settled = false
            fallback()
          }
          return
        }

        if (event.type === 'job_failed') {
          settled = true
          status.value = 'error'
          lastError.value = event.error_message || failedFallbackMessage
          transportMode.value = 'idle'
          closeLiveSocket()
          reject(new Error(lastError.value))
        }
      }

      ws.onerror = () => {
        fallback()
      }

      ws.onclose = () => {
        fallback()
      }
    })
  }

  async function runJobLifecycle(job: ForecastJobInfo, token: number, failedMessage: string) {
    currentJob.value = job
    const viaWsDone = await consumeJobViaWs(job.job_id, token, failedMessage)
    if (viaWsDone) return result.value
    return await pollJobUntilDone(job.job_id, token, failedMessage)
  }

  async function runWithParams(params: ScenarioParams) {
    closeLiveSocket()
    activePollToken.value += 1
    const token = activePollToken.value
    status.value = 'queued'
    transportMode.value = 'idle'
    lastError.value = null
    currentJob.value = null
    try {
      const { job } = await createForecastJob(params)
      return await runJobLifecycle(job, token, t('alerts.forecastFailed'))
    } catch (err) {
      status.value = 'error'
      transportMode.value = 'idle'
      lastError.value = err instanceof Error ? err.message : t('alerts.forecastFailed')
      throw err
    }
  }

  async function runSavedScenarioById(id: string) {
    closeLiveSocket()
    activePollToken.value += 1
    const token = activePollToken.value
    status.value = 'queued'
    transportMode.value = 'idle'
    lastError.value = null
    currentJob.value = null
    try {
      const { job } = await runScenario(id)
      return await runJobLifecycle(job, token, t('alerts.runFailed'))
    } catch (err) {
      status.value = 'error'
      transportMode.value = 'idle'
      lastError.value = err instanceof Error ? err.message : t('alerts.runFailed')
      throw err
    }
  }

  async function exportCsv(jobId?: string) {
    const targetJobId = jobId ?? lastSuccessfulJob.value?.job_id
    if (!targetJobId) throw new Error(t('disabledReasons.runRequired'))
    try {
      const blob = await exportForecastCsvByJob(targetJobId)
      downloadBlob(blob, 'forecast.csv')
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : t('alerts.exportFailed')
      throw err
    }
  }

  async function exportXlsx(jobId?: string) {
    const targetJobId = jobId ?? lastSuccessfulJob.value?.job_id
    if (!targetJobId) throw new Error(t('disabledReasons.runRequired'))
    try {
      const blob = await exportForecastXlsxByJob(targetJobId)
      downloadBlob(blob, 'forecast.xlsx')
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : t('alerts.exportFailed')
      throw err
    }
  }

  function reset() {
    closeLiveSocket()
    activePollToken.value += 1
    status.value = 'idle'
    transportMode.value = 'idle'
    result.value = null
    lastSuccessfulResult.value = null
    currentJob.value = null
    lastSuccessfulJob.value = null
    lastRunAt.value = null
    lastError.value = null
  }

  return {
    status,
    running,
    result,
    lastSuccessfulResult,
    currentJob,
    lastSuccessfulJob,
    currentProgress,
    completedRuns,
    totalRuns,
    transportMode,
    lastRunAt,
    lastError,
    runWithParams,
    runSavedScenarioById,
    exportCsv,
    exportXlsx,
    reset,
  }
}
