import { computed, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { listScenarios, loadScenario, saveScenario } from '../services/api'
import type {
  CullGrouping,
  ScenarioInfo,
  ScenarioParams,
  ScenarioPreset,
  UiValidationIssue,
} from '../types/forecast'

type ScenarioEditorOptions = {
  datasetId: Ref<string | null>
  defaultReportDate: Ref<string>
}

type ScenarioFormState = Omit<ScenarioParams, 'dataset_id' | 'seed'> & { seed: number }

function createDefaultFormState(reportDate: string): ScenarioFormState {
  return {
    report_date: reportDate,
    horizon_months: 36,
    future_date: null,
    mc_runs: 50,
    seed: 42,
    service_period: {
      mean_days: 115,
      std_days: 10,
      min_days_after_calving: 50,
    },
    heifer_insem: {
      min_age_days: 365,
      max_age_days: 395,
    },
    culling: {
      estimate_from_dataset: true,
      grouping: 'lactation',
      fallback_monthly_hazard: 0.008,
      age_band_years: 2,
    },
    replacement: {
      enabled: true,
      annual_heifer_ratio: 0.3,
      lookahead_months: 12,
    },
    purchases: [],
  }
}

export function useScenarioEditor(options: ScenarioEditorOptions) {
  const { t } = useI18n()

  const scenarioName = ref(t('common.baseline'))
  const form = ref<ScenarioFormState>(createDefaultFormState(options.defaultReportDate.value))

  const scenarioList = ref<ScenarioInfo[]>([])
  const saving = ref(false)
  const loading = ref(false)
  const scenariosLoading = ref(false)
  const activePreset = ref<ScenarioPreset>('baseline')

  const baselineSnapshot = ref<string>('')

  function snapshotCurrentState() {
    return JSON.stringify({
      scenarioName: scenarioName.value,
      form: form.value,
    })
  }

  function markBaseline() {
    baselineSnapshot.value = snapshotCurrentState()
  }

  function restoreBaseline() {
    if (!baselineSnapshot.value) return
    const parsed = JSON.parse(baselineSnapshot.value) as {
      scenarioName: string
      form: ScenarioFormState
    }
    scenarioName.value = parsed.scenarioName
    form.value = parsed.form
  }

  const isDirty = computed(() => snapshotCurrentState() !== baselineSnapshot.value)

  const validationIssues = computed<UiValidationIssue[]>(() => {
    const issues: UiValidationIssue[] = []
    const f = form.value

    if (!f.report_date) {
      issues.push({ field: 'report_date', severity: 'error', message: t('validation.reportDateRequired') })
    }
    if (f.horizon_months < 1 || f.horizon_months > 120) {
      issues.push({ field: 'horizon_months', severity: 'error', message: t('validation.horizonRange') })
    }
    if (f.mc_runs < 1 || f.mc_runs > 300) {
      issues.push({ field: 'mc_runs', severity: 'error', message: t('validation.mcRunsRange') })
    }
    if (f.heifer_insem.min_age_days > f.heifer_insem.max_age_days) {
      issues.push({
        field: 'heifer_insem',
        severity: 'error',
        message: t('validation.heiferAgeRange'),
      })
    }

    f.purchases.forEach((purchase, index) => {
      const hasExpected = Boolean(purchase.expected_calving_date)
      const hasDays = purchase.days_pregnant !== null && purchase.days_pregnant !== undefined

      if (!purchase.date_in) {
        issues.push({
          field: `purchases.${index}.date_in`,
          severity: 'error',
          message: t('validation.purchaseDateRequired', { index: index + 1 }),
        })
      }
      if (purchase.count < 1 || purchase.count > 5000) {
        issues.push({
          field: `purchases.${index}.count`,
          severity: 'error',
          message: t('validation.purchaseCountRange', { index: index + 1 }),
        })
      }
      if (hasExpected && hasDays) {
        issues.push({
          field: `purchases.${index}`,
          severity: 'error',
          message: t('validation.purchaseMutualExclusive', { index: index + 1 }),
        })
      }
      if (!hasExpected && !hasDays) {
        issues.push({
          field: `purchases.${index}`,
          severity: 'error',
          message: t('validation.purchaseOneRequired', { index: index + 1 }),
        })
      }
    })

    return issues
  })

  const hasErrors = computed(() => validationIssues.value.some(x => x.severity === 'error'))

  function addPurchase() {
    form.value.purchases.push({
      date_in: form.value.report_date || '',
      count: 10,
      expected_calving_date: null,
      days_pregnant: 150,
    })
  }

  function removePurchase(index: number) {
    form.value.purchases.splice(index, 1)
  }

  function setGrouping(value: CullGrouping) {
    form.value.culling.grouping = value
  }

  function applyPreset(preset: ScenarioPreset) {
    activePreset.value = preset
    if (preset === 'baseline') {
      form.value.service_period = { mean_days: 115, std_days: 10, min_days_after_calving: 50 }
      form.value.heifer_insem = { min_age_days: 365, max_age_days: 395 }
      form.value.culling.fallback_monthly_hazard = 0.008
      form.value.replacement.annual_heifer_ratio = 0.3
      return
    }
    if (preset === 'conservative') {
      form.value.service_period = { mean_days: 125, std_days: 12, min_days_after_calving: 60 }
      form.value.heifer_insem = { min_age_days: 375, max_age_days: 410 }
      form.value.culling.fallback_monthly_hazard = 0.012
      form.value.replacement.annual_heifer_ratio = 0.25
      return
    }
    form.value.service_period = { mean_days: 105, std_days: 8, min_days_after_calving: 50 }
    form.value.heifer_insem = { min_age_days: 350, max_age_days: 385 }
    form.value.culling.fallback_monthly_hazard = 0.006
    form.value.replacement.annual_heifer_ratio = 0.35
  }

  function buildParams(): ScenarioParams {
    if (!options.datasetId.value) {
      throw new Error(t('disabledReasons.datasetRequired'))
    }
    return {
      dataset_id: options.datasetId.value,
      report_date: form.value.report_date,
      horizon_months: form.value.horizon_months,
      future_date: form.value.future_date || null,
      mc_runs: form.value.mc_runs,
      seed: form.value.seed,
      service_period: { ...form.value.service_period },
      heifer_insem: { ...form.value.heifer_insem },
      culling: { ...form.value.culling },
      replacement: { ...form.value.replacement },
      purchases: form.value.purchases.map(x => ({ ...x })),
    }
  }

  function setFromScenarioParams(params: ScenarioParams) {
    form.value = {
      report_date: params.report_date,
      horizon_months: params.horizon_months,
      future_date: params.future_date || null,
      mc_runs: params.mc_runs,
      seed: params.seed,
      service_period: { ...params.service_period },
      heifer_insem: { ...params.heifer_insem },
      culling: { ...params.culling },
      replacement: { ...params.replacement },
      purchases: (params.purchases || []).map(x => ({ ...x })),
    }
  }

  async function refreshScenarioList() {
    if (!options.datasetId.value) {
      scenarioList.value = []
      return
    }
    scenariosLoading.value = true
    try {
      const all = await listScenarios()
      scenarioList.value = all.filter(x => x.dataset_id === options.datasetId.value)
    } finally {
      scenariosLoading.value = false
    }
  }

  async function saveCurrentScenario() {
    if (!options.datasetId.value || hasErrors.value || !scenarioName.value.trim()) return
    saving.value = true
    try {
      await saveScenario(scenarioName.value.trim(), buildParams())
      await refreshScenarioList()
      markBaseline()
    } finally {
      saving.value = false
    }
  }

  async function loadScenarioById(id: string) {
    loading.value = true
    try {
      const detail = await loadScenario(id)
      scenarioName.value = detail.name
      setFromScenarioParams(detail.params)
      markBaseline()
    } finally {
      loading.value = false
    }
  }

  function resetForNewDataset(reportDate: string) {
    form.value = createDefaultFormState(reportDate)
    scenarioName.value = t('common.baseline')
    activePreset.value = 'baseline'
    markBaseline()
  }

  watch(
    () => options.defaultReportDate.value,
    reportDate => {
      if (!form.value.report_date && reportDate) {
        form.value.report_date = reportDate
      }
    },
  )

  markBaseline()

  return {
    scenarioName,
    form,
    saving,
    loading,
    scenariosLoading,
    scenarioList,
    activePreset,
    validationIssues,
    hasErrors,
    isDirty,
    setGrouping,
    addPurchase,
    removePurchase,
    applyPreset,
    buildParams,
    setFromScenarioParams,
    refreshScenarioList,
    saveCurrentScenario,
    loadScenarioById,
    resetForNewDataset,
    restoreBaseline,
    markBaseline,
  }
}

export type ScenarioEditorStore = ReturnType<typeof useScenarioEditor>
