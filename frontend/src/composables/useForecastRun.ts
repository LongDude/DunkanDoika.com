import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { exportForecastCsv, exportForecastXlsx, runForecast, runScenario } from '../services/api'
import type { ForecastResult, ScenarioParams } from '../types/forecast'

type RunStatus = 'idle' | 'running' | 'success' | 'error'

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
  const running = computed(() => status.value === 'running')
  const result = ref<ForecastResult | null>(null)
  const lastSuccessfulResult = ref<ForecastResult | null>(null)
  const lastRunAt = ref<string | null>(null)
  const lastError = ref<string | null>(null)

  async function runWithParams(params: ScenarioParams) {
    status.value = 'running'
    lastError.value = null
    try {
      result.value = await runForecast(params)
      lastSuccessfulResult.value = result.value
      lastRunAt.value = new Date().toISOString()
      status.value = 'success'
      return result.value
    } catch (err) {
      status.value = 'error'
      lastError.value = err instanceof Error ? err.message : t('alerts.forecastFailed')
      throw err
    }
  }

  async function runSavedScenarioById(id: string) {
    status.value = 'running'
    lastError.value = null
    try {
      result.value = await runScenario(id)
      lastSuccessfulResult.value = result.value
      lastRunAt.value = new Date().toISOString()
      status.value = 'success'
      return result.value
    } catch (err) {
      status.value = 'error'
      lastError.value = err instanceof Error ? err.message : t('alerts.runFailed')
      throw err
    }
  }

  async function exportCsv(params: ScenarioParams) {
    try {
      const blob = await exportForecastCsv(params)
      downloadBlob(blob, 'forecast.csv')
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : t('alerts.exportFailed')
      throw err
    }
  }

  async function exportXlsx(params: ScenarioParams) {
    try {
      const blob = await exportForecastXlsx(params)
      downloadBlob(blob, 'forecast.xlsx')
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : t('alerts.exportFailed')
      throw err
    }
  }

  return {
    status,
    running,
    result,
    lastSuccessfulResult,
    lastRunAt,
    lastError,
    runWithParams,
    runSavedScenarioById,
    exportCsv,
    exportXlsx,
  }
}
