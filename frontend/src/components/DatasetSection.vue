<template>
  <section class="card">
    <h2>{{ t('dataset.sectionTitle') }}</h2>
    <div class="row">
      <input type="file" accept=".csv" @change="onFile" />
      <button @click="onRefreshScenarios" :disabled="!dataset">{{ t('dataset.refreshScenarios') }}</button>
    </div>
    <div v-if="dataset" class="muted">
      <div class="grid3">
        <div><b>{{ t('dataset.datasetId') }}:</b> <code>{{ dataset.dataset_id }}</code></div>
        <div><b>{{ t('dataset.rows') }}:</b> {{ dataset.n_rows }}</div>
        <div><b>{{ t('dataset.reportDateSuggested') }}:</b> {{ dataset.report_date_suggested ?? t('common.notAvailable') }}</div>
      </div>
      <details style="margin-top:10px">
        <summary>{{ t('dataset.statusesFromCsv') }}</summary>
        <div class="chips">
          <span class="chip" v-for="(value, key) in dataset.status_counts" :key="key">{{ key }}: {{ value }}</span>
        </div>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DatasetUploadResponse } from '../types/forecast'

defineProps<{
  dataset: DatasetUploadResponse | null
  onFile: (e: Event) => void | Promise<void>
  onRefreshScenarios: () => void | Promise<void>
}>()

const { t } = useI18n()
</script>
