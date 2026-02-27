<template>
  <section class="card">
    <h2>{{ t('comparison.chartTitle') }}</h2>
    <div v-if="!baseItem" class="empty-state">{{ t('comparison.empty') }}</div>
    <canvas v-else ref="canvas"></canvas>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Chart from 'chart.js/auto'
import type { CompareItem } from '../types/forecast'

const props = defineProps<{
  baseItem: CompareItem | null
  items: CompareItem[]
}>()

const { t, locale } = useI18n()
const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null

function toNumberOrNull(value: number | null | undefined) {
  return value === null || value === undefined ? null : Number(value)
}

function render() {
  if (!props.baseItem || !canvas.value) return
  const basePoints = props.baseItem.res.series_p50.points
  const labels = basePoints.map(p => p.date)
  const datasets: any[] = [
    {
      label: t('comparison.baseLabel', { name: props.baseItem.label }),
      data: basePoints.map(p => toNumberOrNull(p.avg_days_in_milk)),
      pointRadius: 0,
      borderWidth: 2,
      tension: 0.2,
    },
  ]

  for (const item of props.items) {
    if (item.id === props.baseItem.id) continue
    datasets.push({
      label: item.label,
      data: item.res.series_p50.points.map(p => toNumberOrNull(p.avg_days_in_milk)),
      pointRadius: 0,
      borderWidth: 1.5,
      borderDash: [6, 4],
      tension: 0.2,
    })
  }

  if (chart) chart.destroy()
  chart = new Chart(canvas.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      parsing: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { title: { display: false, text: t('comparison.chartTitle') } },
    },
  })
}

watch(
  () => [props.baseItem, props.items, locale.value],
  async () => {
    await nextTick()
    render()
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  if (chart) chart.destroy()
})
</script>
