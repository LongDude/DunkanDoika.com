<template>
  <div class="wrap">
    <h1>Dairy Forecast</h1>

    <section class="card">
      <h2>1) Датасет</h2>
      <div class="row">
        <input type="file" accept=".csv" @change="onFile" />
        <button @click="refreshScenarios" :disabled="!dataset">Обновить список сценариев</button>
      </div>
      <div v-if="dataset" class="muted">
        <div class="grid3">
          <div><b>dataset_id:</b> <code>{{ dataset.dataset_id }}</code></div>
          <div><b>строк:</b> {{ dataset.n_rows }}</div>
          <div><b>report_date (suggested):</b> {{ dataset.report_date_suggested ?? '—' }}</div>
        </div>
        <details style="margin-top:10px">
          <summary>Статусы (из CSV)</summary>
          <div class="chips">
            <span class="chip" v-for="(v,k) in dataset.status_counts" :key="k">{{ k }}: {{ v }}</span>
          </div>
        </details>
      </div>
    </section>

    <section class="card" v-if="dataset">
      <h2>2) Сценарий</h2>

      <div class="row" style="justify-content:space-between; gap:12px; flex-wrap:wrap;">
        <div class="row" style="gap:10px; flex-wrap:wrap;">
          <label class="inline">
            Имя сценария
            <input v-model="scenarioName" placeholder="Напр. Baseline" style="min-width:260px" />
          </label>
          <button @click="saveScenario" :disabled="saving || !scenarioName">Сохранить</button>
          <button @click="runForecast" :disabled="running">Запустить</button>
          <button @click="addToCompare" :disabled="!result">Добавить в сравнение</button>
          <button @click="clearCompare" :disabled="compare.length===0">Очистить сравнение</button>
        </div>

        <div class="row" style="gap:10px; flex-wrap:wrap;">
          <button @click="exportCsv" :disabled="running">Export CSV</button>
          <button @click="exportXlsx" :disabled="running">Export XLSX</button>
        </div>
      </div>

      <div class="grid4" style="margin-top:12px">
        <label>
          report_date
          <input type="date" v-model="reportDate" />
        </label>
        <label>
          horizon (months)
          <input type="number" min="1" max="120" v-model.number="horizonMonths" />
        </label>
        <label>
          future_date (опционально)
          <input type="date" v-model="futureDate" />
        </label>
        <label>
          MC runs
          <input type="number" min="1" max="300" v-model.number="mcRuns" />
        </label>
      </div>

      <details style="margin-top:10px" open>
        <summary>Параметры модели</summary>
        <div class="grid4" style="margin-top:10px">
          <div class="subcard">
            <h3>Сервис-период</h3>
            <label>mean_days <input type="number" v-model.number="spMean" min="50" max="250" /></label>
            <label>std_days <input type="number" v-model.number="spStd" min="0" max="80" /></label>
            <label>min_after_calving <input type="number" v-model.number="spMin" min="0" max="120" /></label>
          </div>
          <div class="subcard">
            <h3>Осеменение тёлок</h3>
            <label>min_age_days <input type="number" v-model.number="hMin" min="250" max="700" /></label>
            <label>max_age_days <input type="number" v-model.number="hMax" min="250" max="800" /></label>
          </div>
          <div class="subcard">
            <h3>Выбытие</h3>
            <label class="row" style="justify-content:space-between; gap:8px">
              <span>estimate_from_dataset</span>
              <input type="checkbox" v-model="cullEstimate" />
            </label>
            <label>grouping
              <select v-model="cullGrouping">
                <option value="lactation">lactation</option>
                <option value="lactation_status">lactation_status</option>
                <option value="age_band">age_band</option>
              </select>
            </label>
            <label>fallback_monthly_hazard <input type="number" step="0.001" v-model.number="cullFallback" min="0" max="0.2" /></label>
            <label>age_band_years <input type="number" v-model.number="cullAgeBand" min="1" max="10" /></label>
          </div>
          <div class="subcard">
            <h3>Ввод нетелей (30%)</h3>
            <label class="row" style="justify-content:space-between; gap:8px">
              <span>enabled</span>
              <input type="checkbox" v-model="replEnabled" />
            </label>
            <label>annual_ratio <input type="number" step="0.01" v-model.number="replRatio" min="0" max="1" /></label>
            <label>lookahead_months <input type="number" v-model.number="replLookahead" min="3" max="36" /></label>
          </div>
        </div>
      </details>

      <details style="margin-top:10px" open>
        <summary>Покупка нетелей</summary>
        <div class="row" style="margin-top:10px; gap:10px; flex-wrap:wrap">
          <button @click="addPurchase">+ Добавить строку</button>
          <span class="muted">Укажите либо expected_calving_date, либо days_pregnant.</span>
        </div>
        <div style="overflow:auto; margin-top:10px">
          <table>
            <thead>
              <tr>
                <th>date_in</th>
                <th>count</th>
                <th>expected_calving_date</th>
                <th>days_pregnant</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, idx) in purchases" :key="idx">
                <td><input type="date" v-model="p.date_in" /></td>
                <td><input type="number" min="1" max="5000" v-model.number="p.count" /></td>
                <td><input type="date" v-model="p.expected_calving_date" /></td>
                <td><input type="number" min="0" max="280" v-model.number="p.days_pregnant" /></td>
                <td><button @click="removePurchase(idx)">Удалить</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <details style="margin-top:10px" v-if="scenarioList.length">
        <summary>Сохранённые сценарии</summary>
        <div style="overflow:auto; margin-top:10px">
          <table>
            <thead><tr><th>name</th><th>created</th><th>report_date</th><th>horizon</th><th></th></tr></thead>
            <tbody>
              <tr v-for="s in scenarioList" :key="s.scenario_id">
                <td><b>{{ s.name }}</b></td>
                <td class="muted">{{ s.created_at }}</td>
                <td>{{ s.report_date }}</td>
                <td>{{ s.horizon_months }}</td>
                <td class="row" style="gap:8px">
                  <button @click="loadScenario(s.scenario_id)">Загрузить</button>
                  <button @click="runScenario(s.scenario_id)">Запустить</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </section>

    <section class="card" v-if="result">
      <h2>Графики</h2>
      <div class="grid2">
        <div>
          <h3>Avg days in milk (DIM)</h3>
          <canvas ref="canvasDim"></canvas>
          <div class="muted" style="margin-top:6px" v-if="compare.length">
            Сравнение (p50):
            <span class="chip" v-for="c in compare" :key="c.id">{{ c.label }}</span>
          </div>
        </div>
        <div>
          <h3>Структура стада (p50)</h3>
          <canvas ref="canvasHerd"></canvas>
        </div>
      </div>

      <div v-if="result.future_point" class="subcard" style="margin-top:12px">
        <h3>Точка на future_date</h3>
        <div class="grid3">
          <div><b>date:</b> {{ result.future_point.date }}</div>
          <div><b>avg DIM:</b> {{ fmt(result.future_point.avg_days_in_milk) }}</div>
          <div><b>milking:</b> {{ result.future_point.milking_count }}</div>
        </div>
      </div>
    </section>

    <section class="card" v-if="result">
      <h2>События по месяцам</h2>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Month</th>
              <th>Calvings</th>
              <th>Dryoffs</th>
              <th>Culls</th>
              <th>Purchases</th>
              <th>Heifer intros</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in result.events" :key="e.month">
              <td>{{ e.month }}</td>
              <td>{{ e.calvings }}</td>
              <td>{{ e.dryoffs }}</td>
              <td>{{ e.culls }}</td>
              <td>{{ e.purchases_in }}</td>
              <td>{{ e.heifer_intros }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import Chart from 'chart.js/auto'

type DatasetUploadResponse = {
  dataset_id: string
  n_rows: number
  report_date_suggested?: string | null
  status_counts: Record<string, number>
}

type ForecastPoint = {
  date: string
  milking_count: number
  dry_count: number
  heifer_count: number
  pregnant_heifer_count: number
  avg_days_in_milk: number | null
}

type ForecastSeries = { points: ForecastPoint[] }

type EventsByMonth = {
  month: string
  calvings: number
  dryoffs: number
  culls: number
  purchases_in: number
  heifer_intros: number
}

type ForecastResult = {
  series_p50: ForecastSeries
  series_p10?: ForecastSeries | null
  series_p90?: ForecastSeries | null
  events: EventsByMonth[]
  future_point?: ForecastPoint | null
}

type PurchaseItem = {
  date_in: string
  count: number
  expected_calving_date?: string | null
  days_pregnant?: number | null
}

type ScenarioInfo = {
  scenario_id: string
  name: string
  created_at: string
  dataset_id: string
  report_date: string
  horizon_months: number
}

type ScenarioDetail = {
  scenario_id: string
  name: string
  created_at: string
  params: any
}

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

// model params
const spMean = ref(115)
const spStd = ref(10)
const spMin = ref(50)

const hMin = ref(365)
const hMax = ref(395)

const cullEstimate = ref(true)
const cullGrouping = ref<'lactation'|'lactation_status'|'age_band'>('lactation')
const cullFallback = ref(0.008)
const cullAgeBand = ref(2)

const replEnabled = ref(true)
const replRatio = ref(0.30)
const replLookahead = ref(12)

const purchases = ref<PurchaseItem[]>([])

const result = ref<ForecastResult | null>(null)
const canvasDim = ref<HTMLCanvasElement | null>(null)
const canvasHerd = ref<HTMLCanvasElement | null>(null)
let chartDim: Chart | null = null
let chartHerd: Chart | null = null

type CompareItem = { id: string; label: string; res: ForecastResult }
const compare = ref<CompareItem[]>([])

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const file = input.files[0]

  const form = new FormData()
  form.append('file', file)

  const resp = await fetch(`${API}/datasets/upload`, { method: 'POST', body: form })
  if (!resp.ok) {
    alert('Upload failed')
    return
  }
  dataset.value = await resp.json()
  reportDate.value = dataset.value.report_date_suggested ?? ''
  await refreshScenarios()
}

function addPurchase() {
  purchases.value.push({ date_in: reportDate.value || '', count: 10, expected_calving_date: null, days_pregnant: 150 })
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
    replacement: { enabled: replEnabled.value, annual_heifer_ratio: replRatio.value, lookahead_months: replLookahead.value },
    culling: {
      estimate_from_dataset: cullEstimate.value,
      grouping: cullGrouping.value,
      fallback_monthly_hazard: cullFallback.value,
      age_band_years: cullAgeBand.value,
    },
    service_period: { mean_days: spMean.value, std_days: spStd.value, min_days_after_calving: spMin.value },
    heifer_insem: { min_age_days: hMin.value, max_age_days: hMax.value },
    purchases: purchases.value.map(p => {
      const hasECD = !!p.expected_calving_date
      const hasDP = p.days_pregnant !== null && p.days_pregnant !== undefined
      return {
        date_in: p.date_in,
        count: p.count,
        expected_calving_date: hasECD ? p.expected_calving_date : null,
        // if neither specified, keep a sane default
        days_pregnant: hasECD ? null : (hasDP ? p.days_pregnant : 150),
      }
    }),
  }
}

async function runForecast() {
  if (!dataset.value) return
  if (!reportDate.value) {
    alert('Set report_date')
    return
  }
  running.value = true
  try {
    const body = buildParams()
    const resp = await fetch(`${API}/forecast/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) {
      const t = await resp.text()
      alert('Forecast failed: ' + t)
      return
    }
    result.value = await resp.json()
    await nextTick()
    renderCharts()
  } finally {
    running.value = false
  }
}

function fmt(v: number | null | undefined) {
  if (v === null || v === undefined) return '—'
  return v.toFixed(1)
}

function renderCharts() {
  if (!result.value) return
  renderDimChart()
  renderHerdChart()
}

function renderDimChart() {
  if (!result.value || !canvasDim.value) return
  const pts = result.value.series_p50.points
  const labels = pts.map(p => p.date)

  const datasets: any[] = []

  // optional band for active result
  if (result.value.series_p10 && result.value.series_p90) {
    const p10 = result.value.series_p10.points.map(p => p.avg_days_in_milk)
    const p90 = result.value.series_p90.points.map(p => p.avg_days_in_milk)
    datasets.push({ label: 'p10', data: p10, pointRadius: 0, borderWidth: 1, fill: false })
    datasets.push({ label: 'p90', data: p90, pointRadius: 0, borderWidth: 1, fill: '-1' })
  }

  datasets.push({
    label: `${scenarioName.value} (p50)`,
    data: pts.map(p => p.avg_days_in_milk),
    tension: 0.25,
    pointRadius: 0,
  })

  for (const c of compare.value) {
    const cpts = c.res.series_p50.points
    datasets.push({ label: `${c.label} (p50)`, data: cpts.map(p => p.avg_days_in_milk), tension: 0.25, pointRadius: 0 })
  }

  if (chartDim) chartDim.destroy()
  chartDim = new Chart(canvasDim.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      parsing: false,
      interaction: { mode: 'index', intersect: false },
      scales: { x: { display: true }, y: { display: true } },
    },
  })
}

function renderHerdChart() {
  if (!result.value || !canvasHerd.value) return
  const pts = result.value.series_p50.points
  const labels = pts.map(p => p.date)

  const milking = pts.map(p => p.milking_count)
  const dry = pts.map(p => p.dry_count)
  const heifer = pts.map(p => p.heifer_count)
  const preg = pts.map(p => p.pregnant_heifer_count)

  if (chartHerd) chartHerd.destroy()
  chartHerd = new Chart(canvasHerd.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Milking', data: milking, fill: true, pointRadius: 0, stack: 's' },
        { label: 'Dry', data: dry, fill: true, pointRadius: 0, stack: 's' },
        { label: 'Heifer', data: heifer, fill: true, pointRadius: 0, stack: 's' },
        { label: 'Pregnant heifer', data: preg, fill: true, pointRadius: 0, stack: 's' },
      ],
    },
    options: {
      responsive: true,
      parsing: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { display: true },
        y: { display: true, stacked: true },
      },
    },
  })
}

function addToCompare() {
  if (!result.value) return
  const id = crypto.randomUUID()
  compare.value.push({ id, label: scenarioName.value, res: result.value })
  nextTick(() => renderDimChart())
}

function clearCompare() {
  compare.value = []
  nextTick(() => renderDimChart())
}

async function exportCsv() {
  if (!dataset.value) return
  const body = buildParams()
  const resp = await fetch(`${API}/forecast/export/csv`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!resp.ok) return alert('Export failed')
  const blob = await resp.blob()
  downloadBlob(blob, 'forecast.csv')
}

async function exportXlsx() {
  if (!dataset.value) return
  const body = buildParams()
  const resp = await fetch(`${API}/forecast/export/xlsx`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!resp.ok) return alert('Export failed')
  const blob = await resp.blob()
  downloadBlob(blob, 'forecast.xlsx')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function refreshScenarios() {
  if (!dataset.value) return
  const resp = await fetch(`${API}/scenarios`)
  if (!resp.ok) return
  const all: ScenarioInfo[] = await resp.json()
  scenarioList.value = all.filter(s => s.dataset_id === dataset.value!.dataset_id)
}

async function saveScenario() {
  if (!dataset.value) return
  if (!scenarioName.value) return
  saving.value = true
  try {
    const body = { name: scenarioName.value, params: buildParams() }
    const resp = await fetch(`${API}/scenarios`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!resp.ok) {
      const t = await resp.text()
      return alert('Save failed: ' + t)
    }
    await refreshScenarios()
  } finally {
    saving.value = false
  }
}

async function loadScenario(id: string) {
  const resp = await fetch(`${API}/scenarios/${id}`)
  if (!resp.ok) return alert('Load failed')
  const s: ScenarioDetail = await resp.json()
  scenarioName.value = s.name
  const p = s.params
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

  purchases.value = (p.purchases || []).map((x: any) => ({
    date_in: x.date_in,
    count: x.count,
    expected_calving_date: x.expected_calving_date,
    days_pregnant: x.days_pregnant,
  }))
}

async function runScenario(id: string) {
  running.value = true
  try {
    const resp = await fetch(`${API}/scenarios/${id}/run`, { method: 'POST' })
    if (!resp.ok) {
      const t = await resp.text()
      return alert('Run failed: ' + t)
    }
    result.value = await resp.json()
    await nextTick()
    renderCharts()
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.wrap { max-width: 1200px; margin: 24px auto; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; }
.card { background: #fff; border: 1px solid #e6e6e6; border-radius: 12px; padding: 16px; margin: 14px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.subcard { background: #fafafa; border: 1px solid #eee; border-radius: 12px; padding: 12px; }
.row { display: flex; gap: 12px; align-items: center; }
.grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.grid3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.grid4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
label { display: grid; gap: 6px; font-size: 14px; color: #333; }
label.inline { display: flex; flex-direction: column; gap: 6px; }
input, button, select { padding: 8px 10px; border-radius: 8px; border: 1px solid #ccc; }
button { cursor: pointer; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: left; font-size: 14px; }
.muted { color: #666; font-size: 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip { display: inline-flex; border: 1px solid #e4e4e4; background: #f7f7f7; padding: 3px 8px; border-radius: 999px; font-size: 12px; }
code { background: #f2f2f2; padding: 2px 6px; border-radius: 6px; }
h3 { margin: 0 0 8px 0; font-size: 15px; }
@media (max-width: 980px) {
  .grid4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid2 { grid-template-columns: 1fr; }
}
</style>
