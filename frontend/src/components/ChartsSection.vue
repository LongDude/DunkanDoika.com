<template>
  <section class="card">
    <h2>{{ t('charts.sectionTitle') }}</h2>
    <div class="grid2">
      <div>
        <h3>{{ t('charts.dimTitle') }}</h3>
        <canvas ref="canvasDim"></canvas>
        <div class="muted" style="margin-top:6px" v-if="compare.length">
          {{ t('charts.compareLabel') }}:
          <span class="chip" v-for="item in compare" :key="item.id">{{ item.label }}</span>
        </div>
      </div>
      <div>
        <h3>{{ t('charts.herdTitle') }}</h3>
        <canvas ref="canvasHerd"></canvas>
      </div>
    </div>

    <div v-if="result.future_point" class="subcard" style="margin-top:12px">
      <h3>{{ t('charts.futurePointTitle') }}</h3>
      <div class="grid3">
        <div><b>{{ t('charts.date') }}:</b> {{ result.future_point.date }}</div>
        <div><b>{{ t('charts.avgDim') }}:</b> {{ fmt(result.future_point.avg_days_in_milk) }}</div>
        <div><b>{{ t('charts.milking') }}:</b> {{ result.future_point.milking_count }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Chart from 'chart.js/auto'
import type { CompareItem, ForecastResult } from '../types/forecast'

const props = defineProps<{
  result: ForecastResult
  compare: CompareItem[]
  scenarioName: string
  fmt: (v: number | null | undefined) => string
}>()

const { t, locale } = useI18n()

const canvasDim = ref<HTMLCanvasElement | null>(null)
const canvasHerd = ref<HTMLCanvasElement | null>(null)

let chartDim: Chart | null = null
let chartHerd: Chart | null = null

function toNumberOrNull(v: number | null | undefined) {
  return v === null || v === undefined ? null : Number(v)
}

function renderDimChart() {
  if (!canvasDim.value) return
  const pts = props.result.series_p50.points
  const labels = pts.map(p => p.date)

  const datasets: any[] = []

  if (props.result.series_p10 && props.result.series_p90) {
    const p10 = props.result.series_p10.points.map(p => toNumberOrNull(p.avg_days_in_milk))
    const p90 = props.result.series_p90.points.map(p => toNumberOrNull(p.avg_days_in_milk))
    datasets.push({ label: t('charts.p10'), data: p10, pointRadius: 0, borderWidth: 1, fill: false })
    datasets.push({ label: t('charts.p90'), data: p90, pointRadius: 0, borderWidth: 1, fill: '-1' })
  }

  datasets.push({
    label: `${props.scenarioName} (${t('charts.p50')})`,
    data: pts.map(p => toNumberOrNull(p.avg_days_in_milk)),
    tension: 0.25,
    pointRadius: 0,
  })

  for (const item of props.compare) {
    const comparePoints = item.res.series_p50.points
    datasets.push({
      label: `${item.label} (${t('charts.p50')})`,
      data: comparePoints.map(p => toNumberOrNull(p.avg_days_in_milk)),
      tension: 0.25,
      pointRadius: 0,
    })
  }

  if (chartDim) chartDim.destroy()
  chartDim = new Chart(canvasDim.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      parsing: true,
      spanGaps: true,
      interaction: { mode: 'index', intersect: false },
      scales: { x: { display: true }, y: { display: true } },
    },
  })
}

function renderHerdChart() {
  if (!canvasHerd.value) return
  const pts = props.result.series_p50.points
  const labels = pts.map(p => p.date)

  const milking = pts.map(p => Number(p.milking_count))
  const dry = pts.map(p => Number(p.dry_count))
  const heifer = pts.map(p => Number(p.heifer_count))
  const pregnant = pts.map(p => Number(p.pregnant_heifer_count))

  if (chartHerd) chartHerd.destroy()
  chartHerd = new Chart(canvasHerd.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: t('charts.herdMilking'), data: milking, pointRadius: 0, tension: 0.2 },
        { label: t('charts.herdDry'), data: dry, pointRadius: 0, tension: 0.2 },
        { label: t('charts.herdHeifer'), data: heifer, pointRadius: 0, tension: 0.2 },
        { label: t('charts.herdPregnantHeifer'), data: pregnant, pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      parsing: true,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { display: true },
        y: { display: true },
      },
    },
  })
}

async function renderCharts() {
  await nextTick()
  renderDimChart()
  renderHerdChart()
}

watch(
  () => [props.result, props.compare, props.scenarioName, locale.value],
  () => { void renderCharts() },
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  if (chartDim) chartDim.destroy()
  if (chartHerd) chartHerd.destroy()
})
</script>
