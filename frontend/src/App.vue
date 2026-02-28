<template>
  <AppShell :active-screen="activeScreen" @change-screen="activeScreen = $event">
    <section v-if="activeScreen === 'dataset'" class="screen-stack">
      <DatasetQualityPanel
        :dataset="workspace.datasetFlow.dataset.value"
        :issues="workspace.datasetFlow.qualityIssues.value"
        @file-change="handleFileInput"
        @refresh="workspace.refreshScenarioList"
      />
    </section>

    <section v-if="activeScreen === 'scenarios'" class="screen-stack">
      <ScenarioFormBasic
        :editor="workspace.editor"
        @apply-preset="workspace.editor.applyPreset"
        @load-scenario="workspace.loadScenarioById"
        @run-scenario="handleRunSavedScenario"
      />
      <ScenarioFormAdvanced :editor="workspace.editor" />
    </section>

    <section v-if="activeScreen === 'forecast'" class="screen-stack">
      <section class="card run-status-card">
        <h2>{{ t('screen.forecast') }}</h2>
        <p>{{ runStatusLabel }}</p>
        <p v-if="workspace.runLayer.running.value" class="muted">
          {{ t('run.progress') }}: {{ workspace.runLayer.currentProgress.value }}%
        </p>
        <p v-if="workspace.runLayer.running.value && workspace.runLayer.totalRuns.value > 0" class="muted">
          {{ t('run.completedRuns') }}:
          {{ workspace.runLayer.completedRuns.value }}/{{ workspace.runLayer.totalRuns.value }}
        </p>
        <p v-if="workspace.runLayer.lastRunAt.value" class="muted">
          {{ t('run.lastRunAt') }}: {{ formattedLastRunAt }}
        </p>
        <p v-if="resultDimModeLabel" class="muted">
          {{ t('run.dimMode') }}: {{ resultDimModeLabel }}
        </p>
        <p v-if="workspace.runLayer.result.value?.meta?.simulation_version" class="muted">
          {{ t('run.simulationVersion') }}: {{ workspace.runLayer.result.value?.meta?.simulation_version }}
        </p>
      </section>

      <ForecastKpiCards :snapshot="kpiSnapshot" />
      <ForecastChartsPanel
        :result="workspace.runLayer.result.value"
        :scenario-name="workspace.editor.scenarioName.value"
        :compare-items="workspace.comparison.items.value"
      />

      <section v-if="workspace.runLayer.result.value" class="card">
        <h2>{{ t('events.title') }}</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ t('events.month') }}</th>
                <th>{{ t('events.calvings') }}</th>
                <th>{{ t('events.dryoffs') }}</th>
                <th>{{ t('events.culls') }}</th>
                <th>{{ t('events.purchases') }}</th>
                <th>{{ t('events.heiferIntros') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="eventItem in workspace.runLayer.result.value.events" :key="eventItem.month">
                <td>{{ formatDate(eventItem.month, currentLocale) }}</td>
                <td>{{ formatNumber(eventItem.calvings, currentLocale) }}</td>
                <td>{{ formatNumber(eventItem.dryoffs, currentLocale) }}</td>
                <td>{{ formatNumber(eventItem.culls, currentLocale) }}</td>
                <td>{{ formatNumber(eventItem.purchases_in, currentLocale) }}</td>
                <td>{{ formatNumber(eventItem.heifer_intros, currentLocale) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </section>

    <section v-if="activeScreen === 'comparison'" class="screen-stack">
      <ComparisonTable
        :base-id="workspace.comparison.baseId.value"
        :base-item="workspace.comparison.baseItem.value"
        :items="workspace.comparison.items.value"
        :rows="workspace.comparison.deltaRows.value"
        @change-base="workspace.comparison.baseId.value = $event"
        @remove-item="workspace.comparison.removeScenario"
      />
      <ComparisonCharts
        :base-item="workspace.comparison.baseItem.value"
        :items="workspace.comparison.items.value"
      />
    </section>

    <section v-if="activeScreen === 'export'" class="screen-stack">
      <section class="card">
        <h2>{{ t('export.title') }}</h2>
        <p>{{ t('export.hint') }}</p>
        <ul class="export-notes">
          <li>{{ t('export.csv') }}</li>
          <li>{{ t('export.xlsx') }}</li>
        </ul>
        <div class="row">
          <button
            :disabled="workspace.exportDisabledReason.value.disabled"
            :title="workspace.exportDisabledReason.value.reason ?? ''"
            @click="workspace.exportCsv"
          >
            {{ t('buttons.exportCsv') }}
          </button>
          <button
            :disabled="workspace.exportDisabledReason.value.disabled"
            :title="workspace.exportDisabledReason.value.reason ?? ''"
            @click="workspace.exportXlsx"
          >
            {{ t('buttons.exportXlsx') }}
          </button>
        </div>
      </section>
    </section>
  </AppShell>

  <ActionFooterBar
    :run-disabled="workspace.runDisabledReason.value"
    :save-disabled="workspace.saveDisabledReason.value"
    :compare-disabled="workspace.compareDisabledReason.value"
    :export-disabled="workspace.exportDisabledReason.value"
    :undo-disabled="workspace.undoDisabledReason.value"
    @run="handleRunForecast"
    @fast-run="handleFastRun"
    @save="workspace.saveScenario"
    @undo="workspace.undoScenarioChanges"
    @add-comparison="workspace.addCurrentToComparison"
    @export-csv="workspace.exportCsv"
    @export-xlsx="workspace.exportXlsx"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from './components/AppShell.vue'
import DatasetQualityPanel from './components/DatasetQualityPanel.vue'
import ScenarioFormBasic from './components/ScenarioFormBasic.vue'
import ScenarioFormAdvanced from './components/ScenarioFormAdvanced.vue'
import ForecastKpiCards from './components/ForecastKpiCards.vue'
import ForecastChartsPanel from './components/ForecastChartsPanel.vue'
import ComparisonTable from './components/ComparisonTable.vue'
import ComparisonCharts from './components/ComparisonCharts.vue'
import ActionFooterBar from './components/ActionFooterBar.vue'
import { useForecastWorkspace } from './composables/useForecastWorkspace'
import { formatDate, formatNumber } from './utils/format'
import type { AppLocale } from './i18n/messages'
import type { ForecastKpiSnapshot } from './types/forecast'

type ScreenId = 'dataset' | 'scenarios' | 'forecast' | 'comparison' | 'export'

const { t, locale } = useI18n()
const workspace = useForecastWorkspace()
const activeScreen = ref<ScreenId>('dataset')

const currentLocale = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)

const runStatusLabel = computed(() => {
  const status = workspace.runLayer.status.value
  return t(`run.${status}`)
})

const formattedLastRunAt = computed(() => formatDate(workspace.runLayer.lastRunAt.value, currentLocale.value))
const resultDimModeLabel = computed(() => {
  const mode = workspace.runLayer.result.value?.meta?.dim_mode
  if (mode === 'from_dataset_field') {
    return t('scenario.dimModeFromDataset')
  }
  if (mode === 'from_calving') {
    return t('scenario.dimModeFromCalving')
  }
  return null
})

const kpiSnapshot = computed<ForecastKpiSnapshot | null>(() => {
  const result = workspace.runLayer.result.value
  if (!result || result.series_p50.points.length === 0) return null
  const first = result.series_p50.points[0]
  const last = result.series_p50.points[result.series_p50.points.length - 1]
  const herdTotal = last.milking_count + last.dry_count
  return {
    date: last.date,
    p50_dim: last.avg_days_in_milk,
    milking_count: last.milking_count,
    dry_ratio: herdTotal > 0 ? last.dry_count / herdTotal : null,
    trend_delta:
      last.avg_days_in_milk === null || first.avg_days_in_milk === null
        ? null
        : last.avg_days_in_milk - first.avg_days_in_milk,
  }
})

async function handleFileInput(event: Event) {
  await workspace.onFileInput(event)
  if (workspace.datasetFlow.dataset.value) {
    activeScreen.value = 'scenarios'
  }
}

async function handleRunForecast() {
  activeScreen.value = 'forecast'
  await workspace.runForecast()
}

async function handleFastRun() {
  activeScreen.value = 'forecast'
  await workspace.fastRun('baseline')
}

async function handleRunSavedScenario(id: string) {
  activeScreen.value = 'forecast'
  await workspace.runSavedScenarioById(id)
}
</script>
