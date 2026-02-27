import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  CompareItem,
  CullGrouping,
  DatasetUploadResponse,
  ForecastResult,
  PurchaseItem,
  ScenarioDetail,
  ScenarioInfo,
} from '../types/forecast'

type ActionResult = Promise<void> | void

export type ForecastPage = {
  dataset: Ref<DatasetUploadResponse | null>
  reportDate: Ref<string>
  horizonMonths: Ref<number>
  mcRuns: Ref<number>
  futureDate: Ref<string>
  running: Ref<boolean>
  scenarioName: Ref<string>
  saving: Ref<boolean>
  scenarioList: Ref<ScenarioInfo[]>
  spMean: Ref<number>
  spStd: Ref<number>
  spMin: Ref<number>
  hMin: Ref<number>
  hMax: Ref<number>
  cullEstimate: Ref<boolean>
  cullGrouping: Ref<CullGrouping>
  cullFallback: Ref<number>
  cullAgeBand: Ref<number>
  replEnabled: Ref<boolean>
  replRatio: Ref<number>
  replLookahead: Ref<number>
  purchases: Ref<PurchaseItem[]>
  result: Ref<ForecastResult | null>
  compare: Ref<CompareItem[]>
  onFile: (e: Event) => ActionResult
  addPurchase: () => void
  removePurchase: (idx: number) => void
  runForecast: () => Promise<void>
  addToCompare: () => void
  clearCompare: () => void
  exportCsv: () => Promise<void>
  exportXlsx: () => Promise<void>
  refreshScenarios: () => Promise<void>
  saveScenario: () => Promise<void>
  loadScenario: (id: string) => Promise<void>
  runScenario: (id: string) => Promise<void>
  fmt: (v: number | null | undefined) => string
}

export function useForecastPage(): ForecastPage {
  const { t } = useI18n()
  const API = import.meta.env.VITE_API_BASE_URL ?? '/api'

  const dataset = ref<DatasetUploadResponse | null>(null)
  const reportDate = ref<string>('')
  const horizonMonths = ref<number>(36)
  const mcRuns = ref<number>(50)
  const futureDate = ref<string>('')
  const running = ref(false)

  const scenarioName = ref('Baseline')
  const saving = ref(false)
  const scenarioList = ref<ScenarioInfo[]>([])

  const spMean = ref(115)
  const spStd = ref(10)
  const spMin = ref(50)

  const hMin = ref(365)
  const hMax = ref(395)

  const cullEstimate = ref(true)
  const cullGrouping = ref<CullGrouping>('lactation')
  const cullFallback = ref(0.008)
  const cullAgeBand = ref(2)

  const replEnabled = ref(true)
  const replRatio = ref(0.3)
  const replLookahead = ref(12)

  const purchases = ref<PurchaseItem[]>([])

  const result = ref<ForecastResult | null>(null)
  const compare = ref<CompareItem[]>([])

  async function onFile(e: Event) {
    const input = e.target as HTMLInputElement
    if (!input.files || input.files.length === 0) return

    const form = new FormData()
    form.append('file', input.files[0])

    const resp = await fetch(`${API}/datasets/upload`, { method: 'POST', body: form })
    if (!resp.ok) {
      alert(t('alerts.uploadFailed'))
      return
    }

    dataset.value = await resp.json()
    reportDate.value = dataset.value.report_date_suggested ?? ''
    await refreshScenarios()
  }

  function addPurchase() {
    purchases.value.push({
      date_in: reportDate.value || '',
      count: 10,
      expected_calving_date: null,
      days_pregnant: 150,
    })
  }

  function removePurchase(idx: number) {
    purchases.value.splice(idx, 1)
  }

  function buildParams() {
    if (!dataset.value) throw new Error('dataset missing')

    return {
      dataset_id: dataset.value.dataset_id,
      report_date: reportDate.value,
      horizon_months: horizonMonths.value,
      future_date: futureDate.value || null,
      mc_runs: mcRuns.value,
      seed: 42,
      replacement: {
        enabled: replEnabled.value,
        annual_heifer_ratio: replRatio.value,
        lookahead_months: replLookahead.value,
      },
      culling: {
        estimate_from_dataset: cullEstimate.value,
        grouping: cullGrouping.value,
        fallback_monthly_hazard: cullFallback.value,
        age_band_years: cullAgeBand.value,
      },
      service_period: {
        mean_days: spMean.value,
        std_days: spStd.value,
        min_days_after_calving: spMin.value,
      },
      heifer_insem: {
        min_age_days: hMin.value,
        max_age_days: hMax.value,
      },
      purchases: purchases.value.map(p => {
        const hasExpectedCalvingDate = Boolean(p.expected_calving_date)
        const hasDaysPregnant = p.days_pregnant !== null && p.days_pregnant !== undefined

        return {
          date_in: p.date_in,
          count: p.count,
          expected_calving_date: hasExpectedCalvingDate ? p.expected_calving_date : null,
          days_pregnant: hasExpectedCalvingDate ? null : (hasDaysPregnant ? p.days_pregnant : 150),
        }
      }),
    }
  }

  async function runForecast() {
    if (!dataset.value) return
    if (!reportDate.value) {
      alert(t('alerts.setReportDate'))
      return
    }

    running.value = true
    try {
      const resp = await fetch(`${API}/forecast/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildParams()),
      })

      if (!resp.ok) {
        const text = await resp.text()
        alert(`${t('alerts.forecastFailed')}: ${text}`)
        return
      }

      result.value = await resp.json()
    } finally {
      running.value = false
    }
  }

  function addToCompare() {
    if (!result.value) return
    compare.value.push({
      id: crypto.randomUUID(),
      label: scenarioName.value,
      res: result.value,
    })
  }

  function clearCompare() {
    compare.value = []
  }

  async function exportCsv() {
    if (!dataset.value) return
    const resp = await fetch(`${API}/forecast/export/csv`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildParams()),
    })
    if (!resp.ok) {
      alert(t('alerts.exportFailed'))
      return
    }
    downloadBlob(await resp.blob(), 'forecast.csv')
  }

  async function exportXlsx() {
    if (!dataset.value) return
    const resp = await fetch(`${API}/forecast/export/xlsx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildParams()),
    })
    if (!resp.ok) {
      alert(t('alerts.exportFailed'))
      return
    }
    downloadBlob(await resp.blob(), 'forecast.xlsx')
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

  async function refreshScenarios() {
    if (!dataset.value) return
    const resp = await fetch(`${API}/scenarios`)
    if (!resp.ok) return
    const allScenarios: ScenarioInfo[] = await resp.json()
    scenarioList.value = allScenarios.filter(s => s.dataset_id === dataset.value!.dataset_id)
  }

  async function saveScenario() {
    if (!dataset.value || !scenarioName.value) return
    saving.value = true
    try {
      const body = { name: scenarioName.value, params: buildParams() }
      const resp = await fetch(`${API}/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const text = await resp.text()
        alert(`${t('alerts.saveFailed')}: ${text}`)
        return
      }
      await refreshScenarios()
    } finally {
      saving.value = false
    }
  }

  async function loadScenario(id: string) {
    const resp = await fetch(`${API}/scenarios/${id}`)
    if (!resp.ok) {
      alert(t('alerts.loadFailed'))
      return
    }

    const scenario: ScenarioDetail = await resp.json()
    scenarioName.value = scenario.name

    const p = scenario.params
    reportDate.value = p.report_date
    horizonMonths.value = p.horizon_months
    futureDate.value = p.future_date || ''
    mcRuns.value = p.mc_runs

    spMean.value = p.service_period.mean_days
    spStd.value = p.service_period.std_days
    spMin.value = p.service_period.min_days_after_calving

    hMin.value = p.heifer_insem.min_age_days
    hMax.value = p.heifer_insem.max_age_days

    cullEstimate.value = p.culling.estimate_from_dataset
    cullGrouping.value = p.culling.grouping
    cullFallback.value = p.culling.fallback_monthly_hazard
    cullAgeBand.value = p.culling.age_band_years

    replEnabled.value = p.replacement.enabled
    replRatio.value = p.replacement.annual_heifer_ratio
    replLookahead.value = p.replacement.lookahead_months

    purchases.value = (p.purchases || []).map((item: any) => ({
      date_in: item.date_in,
      count: item.count,
      expected_calving_date: item.expected_calving_date,
      days_pregnant: item.days_pregnant,
    }))
  }

  async function runScenario(id: string) {
    running.value = true
    try {
      const resp = await fetch(`${API}/scenarios/${id}/run`, { method: 'POST' })
      if (!resp.ok) {
        const text = await resp.text()
        alert(`${t('alerts.runFailed')}: ${text}`)
        return
      }
      result.value = await resp.json()
    } finally {
      running.value = false
    }
  }

  function fmt(v: number | null | undefined) {
    if (v === null || v === undefined) return t('common.notAvailable')
    return v.toFixed(1)
  }

  return {
    dataset,
    reportDate,
    horizonMonths,
    mcRuns,
    futureDate,
    running,
    scenarioName,
    saving,
    scenarioList,
    spMean,
    spStd,
    spMin,
    hMin,
    hMax,
    cullEstimate,
    cullGrouping,
    cullFallback,
    cullAgeBand,
    replEnabled,
    replRatio,
    replLookahead,
    purchases,
    result,
    compare,
    onFile,
    addPurchase,
    removePurchase,
    runForecast,
    addToCompare,
    clearCompare,
    exportCsv,
    exportXlsx,
    refreshScenarios,
    saveScenario,
    loadScenario,
    runScenario,
    fmt,
  }
}
