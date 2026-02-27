import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createForecastJob,
  exportForecastCsvByJob,
  exportForecastXlsxByJob,
  getForecastJob,
  getForecastResult,
  runScenario,
} from '../services/api'
import type { ForecastJobInfo, ForecastResult, ScenarioParams } from '../types/forecast'

type RunStatus = 'idle' | 'queued' | 'running' | 'success' | 'error'

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
  const lastRunAt = ref<string | null>(null)
  const lastError = ref<string | null>(null)
  const activePollToken = ref(0)

  async function pollJobUntilDone(jobId: string, token: number, failedFallbackMessage: string) {
    for (let attempt = 0; attempt < JOB_POLL_MAX_ATTEMPTS; attempt += 1) {
      if (token !== activePollToken.value) return null

      const job = await getForecastJob(jobId)
      currentJob.value = job

      if (job.status === 'queued') {
        status.value = 'queued'
      } else if (job.status === 'running') {
        status.value = 'running'
      } else if (job.status === 'succeeded') {
        status.value = 'running'
        const forecast = await getForecastResult(jobId)
        if (token !== activePollToken.value) return null
        result.value = forecast
        lastSuccessfulResult.value = forecast
        lastSuccessfulJob.value = job
        lastRunAt.value = job.finished_at ?? new Date().toISOString()
        status.value = 'success'
        return forecast
      } else {
        status.value = 'error'
        lastError.value = job.error_message || failedFallbackMessage
        throw new Error(lastError.value)
      }

      await sleep(JOB_POLL_INTERVAL_MS)
    }

    status.value = 'error'
    lastError.value = t('alerts.jobTimeout')
    throw new Error(lastError.value)
  }

  async function runWithParams(params: ScenarioParams) {
    activePollToken.value += 1
    const token = activePollToken.value
    status.value = 'queued'
    lastError.value = null
    currentJob.value = null
    try {
      const { job } = await createForecastJob(params)
      currentJob.value = job
      return await pollJobUntilDone(job.job_id, token, t('alerts.forecastFailed'))
    } catch (err) {
      status.value = 'error'
      lastError.value = err instanceof Error ? err.message : t('alerts.forecastFailed')
      throw err
    }
  }

  async function runSavedScenarioById(id: string) {
    activePollToken.value += 1
    const token = activePollToken.value
    status.value = 'queued'
    lastError.value = null
    currentJob.value = null
    try {
      const { job } = await runScenario(id)
      currentJob.value = job
      return await pollJobUntilDone(job.job_id, token, t('alerts.runFailed'))
    } catch (err) {
      status.value = 'error'
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
    activePollToken.value += 1
    status.value = 'idle'
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
    lastRunAt,
    lastError,
    runWithParams,
    runSavedScenarioById,
    exportCsv,
    exportXlsx,
    reset,
  }
}
