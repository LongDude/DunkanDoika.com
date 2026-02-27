import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useComparison } from './useComparison'
import { useDatasetWorkflow } from './useDatasetWorkflow'
import { useForecastRun } from './useForecastRun'
import { useScenarioEditor } from './useScenarioEditor'
import type { DisabledReason, ScenarioPreset } from '../types/forecast'

function disabled(disabledValue: boolean, reason: string | null): DisabledReason {
  return { disabled: disabledValue, reason: disabledValue ? reason : null }
}

export function useForecastWorkspace() {
  const { t } = useI18n()

  const datasetFlow = useDatasetWorkflow()
  const datasetId = computed(() => datasetFlow.dataset.value?.dataset_id ?? null)
  const defaultReportDate = computed(() => datasetFlow.dataset.value?.report_date_suggested ?? '')

  const editor = useScenarioEditor({ datasetId, defaultReportDate })
  const runLayer = useForecastRun()
  const comparison = useComparison()

  const runDisabledReason = computed<DisabledReason>(() => {
    if (!datasetId.value) return disabled(true, t('disabledReasons.datasetRequired'))
    if (editor.hasErrors.value) return disabled(true, t('disabledReasons.fixValidationErrors'))
    if (runLayer.running.value) return disabled(true, t('disabledReasons.alreadyRunning'))
    return disabled(false, null)
  })

  const saveDisabledReason = computed<DisabledReason>(() => {
    if (!datasetId.value) return disabled(true, t('disabledReasons.datasetRequired'))
    if (!editor.scenarioName.value.trim()) return disabled(true, t('disabledReasons.scenarioNameRequired'))
    if (editor.hasErrors.value) return disabled(true, t('disabledReasons.fixValidationErrors'))
    if (editor.saving.value) return disabled(true, t('disabledReasons.saving'))
    return disabled(false, null)
  })

  const exportDisabledReason = computed<DisabledReason>(() => {
    if (!runLayer.lastSuccessfulJob.value) return disabled(true, t('disabledReasons.runRequired'))
    return disabled(false, null)
  })

  const compareDisabledReason = computed<DisabledReason>(() => {
    if (!runLayer.result.value) return disabled(true, t('disabledReasons.runRequired'))
    if (comparison.items.value.length >= comparison.maxItems) return disabled(true, t('disabledReasons.compareLimit'))
    return disabled(false, null)
  })

  const undoDisabledReason = computed<DisabledReason>(() => {
    if (!editor.isDirty.value) return disabled(true, t('disabledReasons.noChanges'))
    return disabled(false, null)
  })

  async function onFileInput(event: Event) {
    const input = event.target as HTMLInputElement
    if (!input.files || input.files.length === 0) return
    try {
      const info = await datasetFlow.upload(input.files[0])
      editor.resetForNewDataset(info.report_date_suggested ?? '')
      await editor.refreshScenarioList()
      comparison.clear()
      runLayer.reset()
    } catch (err) {
      alert(`${t('alerts.uploadFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function refreshScenarioList() {
    try {
      await editor.refreshScenarioList()
    } catch (err) {
      alert(`${t('alerts.loadFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function runForecast() {
    if (runDisabledReason.value.disabled) return
    try {
      const params = editor.buildParams()
      await runLayer.runWithParams(params)
    } catch (err) {
      alert(`${t('alerts.forecastFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function fastRun(preset: ScenarioPreset = 'baseline') {
    editor.applyPreset(preset)
    await runForecast()
  }

  async function saveScenario() {
    if (saveDisabledReason.value.disabled) return
    try {
      await editor.saveCurrentScenario()
    } catch (err) {
      alert(`${t('alerts.saveFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function loadScenarioById(id: string) {
    try {
      await editor.loadScenarioById(id)
    } catch (err) {
      alert(`${t('alerts.loadFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function runSavedScenarioById(id: string) {
    if (runLayer.running.value) return
    try {
      await runLayer.runSavedScenarioById(id)
    } catch (err) {
      alert(`${t('alerts.runFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function exportCsv() {
    if (exportDisabledReason.value.disabled) return
    try {
      await runLayer.exportCsv()
    } catch (err) {
      alert(`${t('alerts.exportFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  async function exportXlsx() {
    if (exportDisabledReason.value.disabled) return
    try {
      await runLayer.exportXlsx()
    } catch (err) {
      alert(`${t('alerts.exportFailed')}: ${err instanceof Error ? err.message : ''}`)
    }
  }

  function addCurrentToComparison() {
    if (!runLayer.result.value) return
    const res = comparison.addScenario(editor.scenarioName.value, runLayer.result.value)
    if (!res.ok && res.reason) {
      alert(res.reason)
    }
  }

  function undoScenarioChanges() {
    if (undoDisabledReason.value.disabled) return
    editor.restoreBaseline()
  }

  return {
    datasetFlow,
    editor,
    runLayer,
    comparison,
    runDisabledReason,
    saveDisabledReason,
    exportDisabledReason,
    compareDisabledReason,
    undoDisabledReason,
    onFileInput,
    refreshScenarioList,
    runForecast,
    fastRun,
    saveScenario,
    loadScenarioById,
    runSavedScenarioById,
    exportCsv,
    exportXlsx,
    addCurrentToComparison,
    undoScenarioChanges,
  }
}
