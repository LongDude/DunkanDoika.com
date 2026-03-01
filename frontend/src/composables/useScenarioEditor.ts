import { computed, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  bulkDeleteMyPresets,
  createMyPreset,
  deleteMyPreset,
  listMyPresets,
  listScenarios,
  loadScenario,
  saveScenario,
  updateMyPreset,
} from '../services/api'
import type {
  BulkDeleteResponse,
  HerdM5ModelParams,
  PurchasePolicy,
  ScenarioInfo,
  ScenarioMode,
  ScenarioParams,
  ScenarioPreset,
  UiValidationIssue,
  UserPreset,
  UserPresetParams,
} from '../types/forecast'

type ScenarioEditorOptions = {
  datasetId: Ref<string | null>
  defaultReportDate: Ref<string>
}

type ScenarioFormState = Omit<ScenarioParams, 'dataset_id'>

function createDefaultModelParams(): HerdM5ModelParams {
  return {
    min_first_insem_age_days: 365,
    voluntary_waiting_period: 50,
    max_service_period_after_vwp: 300,
    population_regulation: 0.5,
    gestation_lo: 275,
    gestation_hi: 280,
    gestation_mu: 277.5,
    gestation_sigma: 2,
    heifer_birth_prob: 0.5,
    purchased_days_to_calving_lo: 1,
    purchased_days_to_calving_hi: 280,
  }
}

function createDefaultFormState(reportDate: string): ScenarioFormState {
  return {
    report_date: reportDate || null,
    horizon_months: 36,
    future_date: null,
    seed: 42,
    mc_runs: 50,
    mode: 'empirical',
    purchase_policy: 'manual',
    lead_time_days: 90,
    confidence_central: 0.9,
    model: createDefaultModelParams(),
    purchases: [],
  }
}

function normalizeOptionalDate(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null
  const trimmed = String(value).trim()
  return trimmed.length > 0 ? trimmed : null
}

function normalizeOptionalDays(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  return Number.isFinite(value) ? value : null
}

function isFirstOfMonth(value: string | null | undefined): boolean {
  if (!value) return true
  const dt = new Date(value)
  return Number.isFinite(dt.getTime()) && dt.getUTCDate() === 1
}

export function useScenarioEditor(options: ScenarioEditorOptions) {
  const { t } = useI18n()

  const scenarioName = ref(t('common.baseline'))
  const form = ref<ScenarioFormState>(createDefaultFormState(options.defaultReportDate.value))

  const scenarioList = ref<ScenarioInfo[]>([])
  const saving = ref(false)
  const loading = ref(false)
  const scenariosLoading = ref(false)
  const presetsLoading = ref(false)
  const presetsSaving = ref(false)
  const userPresets = ref<UserPreset[]>([])
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
    const datasetReportDate = normalizeOptionalDate(options.defaultReportDate.value)
    const formReportDate = normalizeOptionalDate(f.report_date)

    if (datasetReportDate && formReportDate && datasetReportDate !== formReportDate) {
      issues.push({
        field: 'report_date',
        severity: 'error',
        message: t('validation.reportDateDatasetMismatch', { date: datasetReportDate }),
      })
    }

    if (f.horizon_months < 1 || f.horizon_months > 120) {
      issues.push({ field: 'horizon_months', severity: 'error', message: t('validation.horizonRange') })
    }

    if (f.mc_runs < 1 || f.mc_runs > 30000) {
      issues.push({ field: 'mc_runs', severity: 'error', message: t('validation.mcRunsRange') })
    }

    if (f.confidence_central < 0.5 || f.confidence_central > 0.99) {
      issues.push({ field: 'confidence_central', severity: 'error', message: t('validation.confidenceRange') })
    }

    if (!isFirstOfMonth(f.future_date)) {
      issues.push({ field: 'future_date', severity: 'error', message: t('validation.futureDateMonthStart') })
    }

    if (f.model.gestation_hi < f.model.gestation_lo) {
      issues.push({ field: 'model.gestation', severity: 'error', message: t('validation.modelGestationRange') })
    }

    if (f.model.purchased_days_to_calving_hi < f.model.purchased_days_to_calving_lo) {
      issues.push({
        field: 'model.purchased_days_to_calving',
        severity: 'error',
        message: t('validation.modelPurchasedRange'),
      })
    }

    if (f.purchase_policy !== 'manual' && f.purchases.length > 0) {
      issues.push({
        field: 'purchase_policy',
        severity: 'error',
        message: t('validation.purchasesManualOnly'),
      })
    }

    if (f.purchase_policy === 'manual') {
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
    }

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

  function applyPreset(preset: ScenarioPreset) {
    activePreset.value = preset

    if (preset === 'baseline') {
      form.value.model = createDefaultModelParams()
      form.value.mode = 'empirical'
      form.value.purchase_policy = 'manual'
      form.value.confidence_central = 0.9
      return
    }

    if (preset === 'conservative') {
      form.value.model.population_regulation = 0.85
      form.value.model.max_service_period_after_vwp = 260
      form.value.mode = 'theoretical'
      form.value.purchase_policy = 'manual'
      form.value.confidence_central = 0.9
      return
    }

    form.value.model.population_regulation = 1.0
    form.value.model.max_service_period_after_vwp = 340
    form.value.mode = 'empirical'
    form.value.purchase_policy = 'auto_forecast'
    form.value.lead_time_days = 90
    form.value.confidence_central = 0.75
    form.value.purchases = []
  }

  function buildParams(): ScenarioParams {
    if (!options.datasetId.value) {
      throw new Error(t('disabledReasons.datasetRequired'))
    }
    const datasetReportDate = normalizeOptionalDate(options.defaultReportDate.value)
    const reportDate = datasetReportDate ?? normalizeOptionalDate(form.value.report_date)

    return {
      dataset_id: options.datasetId.value,
      report_date: reportDate,
      horizon_months: form.value.horizon_months,
      future_date: normalizeOptionalDate(form.value.future_date),
      seed: form.value.seed,
      mc_runs: form.value.mc_runs,
      mode: form.value.mode,
      purchase_policy: form.value.purchase_policy,
      lead_time_days: form.value.lead_time_days,
      confidence_central: form.value.confidence_central,
      model: { ...form.value.model },
      purchases:
        form.value.purchase_policy === 'manual'
          ? form.value.purchases.map(x => ({
              date_in: x.date_in,
              count: x.count,
              expected_calving_date: normalizeOptionalDate(x.expected_calving_date),
              days_pregnant: normalizeOptionalDays(x.days_pregnant),
            }))
          : [],
    }
  }

  function setFromScenarioParams(params: ScenarioParams) {
    form.value = {
      report_date: params.report_date || null,
      horizon_months: params.horizon_months,
      future_date: params.future_date || null,
      seed: params.seed,
      mc_runs: params.mc_runs,
      mode: params.mode,
      purchase_policy: params.purchase_policy,
      lead_time_days: params.lead_time_days,
      confidence_central: params.confidence_central,
      model: { ...params.model },
      purchases: (params.purchases || []).map(x => ({ ...x })),
    }
  }

  function buildUserPresetParams(): UserPresetParams {
    const params = buildParams()
    const { dataset_id: _unused, ...presetParams } = params
    return presetParams
  }

  function applyUserPreset(preset: UserPreset) {
    const params = preset.params
    if (!params || preset.is_legacy) {
      throw new Error(preset.legacy_reason || t('presets.legacyReadonly'))
    }

    form.value = {
      report_date: params.report_date || form.value.report_date || options.defaultReportDate.value,
      horizon_months: params.horizon_months,
      future_date: params.future_date || null,
      seed: params.seed,
      mc_runs: params.mc_runs,
      mode: params.mode,
      purchase_policy: params.purchase_policy,
      lead_time_days: params.lead_time_days,
      confidence_central: params.confidence_central,
      model: { ...params.model },
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

  async function refreshUserPresets() {
    presetsLoading.value = true
    try {
      userPresets.value = await listMyPresets()
    } finally {
      presetsLoading.value = false
    }
  }

  async function saveCurrentAsUserPreset(name: string) {
    const trimmed = name.trim()
    if (!trimmed) return null
    presetsSaving.value = true
    try {
      const created = await createMyPreset(trimmed, buildUserPresetParams())
      await refreshUserPresets()
      return created
    } finally {
      presetsSaving.value = false
    }
  }

  async function updateUserPresetById(presetId: string, payload: { name?: string; replaceParams?: boolean }) {
    const body: { name?: string; params?: UserPresetParams } = {}
    if (typeof payload.name === 'string') {
      const trimmed = payload.name.trim()
      if (trimmed) body.name = trimmed
    }
    if (payload.replaceParams) {
      body.params = buildUserPresetParams()
    }
    if (!body.name && !body.params) return null

    presetsSaving.value = true
    try {
      const updated = await updateMyPreset(presetId, body)
      await refreshUserPresets()
      return updated
    } finally {
      presetsSaving.value = false
    }
  }

  async function deleteUserPresetById(presetId: string): Promise<BulkDeleteResponse> {
    presetsSaving.value = true
    try {
      const response = await deleteMyPreset(presetId)
      await refreshUserPresets()
      return response
    } finally {
      presetsSaving.value = false
    }
  }

  async function bulkDeleteUserPresetByIds(ids: string[]): Promise<BulkDeleteResponse> {
    const cleaned = ids.filter(Boolean)
    if (cleaned.length === 0) {
      return { deleted_ids: [], skipped: [] }
    }
    presetsSaving.value = true
    try {
      const response = await bulkDeleteMyPresets(cleaned)
      await refreshUserPresets()
      return response
    } finally {
      presetsSaving.value = false
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
      if (detail.is_legacy || !detail.params) {
        throw new Error(detail.legacy_reason || t('scenario.legacyReadonly'))
      }
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
      if (reportDate && form.value.report_date !== reportDate) {
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
    presetsLoading,
    presetsSaving,
    userPresets,
    activePreset,
    validationIssues,
    hasErrors,
    isDirty,
    addPurchase,
    removePurchase,
    applyPreset,
    buildParams,
    setFromScenarioParams,
    refreshScenarioList,
    refreshUserPresets,
    saveCurrentScenario,
    saveCurrentAsUserPreset,
    updateUserPresetById,
    deleteUserPresetById,
    bulkDeleteUserPresetByIds,
    buildUserPresetParams,
    applyUserPreset,
    loadScenarioById,
    resetForNewDataset,
    restoreBaseline,
    markBaseline,
  }
}

export type ScenarioEditorStore = ReturnType<typeof useScenarioEditor>
