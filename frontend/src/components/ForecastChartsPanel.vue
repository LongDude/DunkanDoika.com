<template>
  <section class="card" v-if="result">
    <h2>{{ t('charts.title') }}</h2>

    <div class="chart-controls">
      <label class="toggle">
        <span>{{ t('charts.showP10') }}</span>
        <input type="checkbox" v-model="showP10" />
      </label>
      <label class="toggle">
        <span>{{ t('charts.showP50') }}</span>
        <input type="checkbox" v-model="showP50" />
      </label>
      <label class="toggle">
        <span>{{ t('charts.showP90') }}</span>
        <input type="checkbox" v-model="showP90" />
      </label>
      <label>
        <span>{{ t('charts.herdMode') }}</span>
        <select v-model="herdMode">
          <option value="line">{{ t('charts.herdLine') }}</option>
          <option value="stacked">{{ t('charts.herdStacked') }}</option>
        </select>
      </label>
    </div>

    <div class="charts-grid">
      <article class="subcard">
        <h3>{{ t('charts.dim') }}</h3>
        <canvas ref="dimCanvas"></canvas>
      </article>
      <article class="subcard">
        <h3>{{ t('charts.herd') }}</h3>
        <canvas ref="herdCanvas"></canvas>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Chart from 'chart.js/auto'
import type { CompareItem, ForecastResult } from '../types/forecast'

const props = defineProps<{
  result: ForecastResult | null
  scenarioName: string
  compareItems: CompareItem[]
}>()

const { t, locale } = useI18n()

const showP10 = ref(true)
const showP50 = ref(true)
const showP90 = ref(true)
const herdMode = ref<'line' | 'stacked'>('line')

const dimCanvas = ref<HTMLCanvasElement | null>(null)
const herdCanvas = ref<HTMLCanvasElement | null>(null)

let dimChart: Chart | null = null
let herdChart: Chart | null = null

function toNumberOrNull(value: number | null | undefined) {
  return value === null || value === undefined ? null : Number(value)
}

function renderDimChart() {
  if (!props.result || !dimCanvas.value) return
  const points = props.result.series_p50.points
  const labels = points.map(point => point.date)
  const datasets: any[] = []

  if (showP10.value && props.result.series_p10) {
    datasets.push({
      label: t('charts.p10Label'),
      data: props.result.series_p10.points.map(point => toNumberOrNull(point.avg_days_in_milk)),
      pointRadius: 0,
      borderWidth: 1,
      tension: 0.2,
    })
  }
  if (showP50.value) {
    datasets.push({
      label: t('charts.seriesP50', { name: props.scenarioName }),
      data: points.map(point => toNumberOrNull(point.avg_days_in_milk)),
      pointRadius: 0,
      borderWidth: 2,
      tension: 0.2,
    })
  }
  if (showP90.value && props.result.series_p90) {
    datasets.push({
      label: t('charts.p90Label'),
      data: props.result.series_p90.points.map(point => toNumberOrNull(point.avg_days_in_milk)),
      pointRadius: 0,
      borderWidth: 1,
      tension: 0.2,
    })
  }
  for (const compare of props.compareItems) {
    datasets.push({
      label: t('charts.seriesP50', { name: compare.label }),
      data: compare.res.series_p50.points.map(point => toNumberOrNull(point.avg_days_in_milk)),
      pointRadius: 0,
      borderDash: [8, 4],
      borderWidth: 1.5,
      tension: 0.2,
    })
  }

  if (dimChart) dimChart.destroy()
  dimChart = new Chart(dimCanvas.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      parsing: true,
      interaction: { mode: 'index', intersect: false },
      scales: { x: { display: true }, y: { display: true } },
    },
  })
}

function herdDataset(label: string, data: number[], fill: boolean) {
  return {
    label,
    data,
    pointRadius: 0,
    fill,
    tension: 0.2,
  }
}

function renderHerdChart() {
  if (!props.result || !herdCanvas.value) return
  const points = props.result.series_p50.points
  const labels = points.map(point => point.date)
  const stacked = herdMode.value === 'stacked'

  const milking = points.map(point => Number(point.milking_count))
  const dry = points.map(point => Number(point.dry_count))
  const heifer = points.map(point => Number(point.heifer_count))
  const pregnant = points.map(point => Number(point.pregnant_heifer_count))

  if (herdChart) herdChart.destroy()
  herdChart = new Chart(herdCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        herdDataset(t('charts.milking'), milking, stacked),
        herdDataset(t('charts.dry'), dry, stacked),
        herdDataset(t('charts.heifer'), heifer, stacked),
        herdDataset(t('charts.pregnantHeifer'), pregnant, stacked),
      ],
    },
    options: {
      responsive: true,
      parsing: true,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { display: true, stacked },
        y: { display: true, stacked },
      },
    },
  })
}

async function renderAll() {
  await nextTick()
  renderDimChart()
  renderHerdChart()
}

watch(
  () => [props.result, props.compareItems, props.scenarioName, showP10.value, showP50.value, showP90.value, herdMode.value, locale.value],
  () => {
    void renderAll()
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  if (dimChart) dimChart.destroy()
  if (herdChart) herdChart.destroy()
})
</script>
