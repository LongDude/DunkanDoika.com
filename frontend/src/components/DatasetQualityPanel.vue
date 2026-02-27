<template>
  <section class="card">
    <h2>{{ t('screen.dataset') }}</h2>
    <div class="upload-row">
      <label class="upload-label">
        <span>{{ t('dataset.uploadLabel') }}</span>
        <input type="file" accept=".csv" @change="$emit('file-change', $event)" />
      </label>
      <button @click="$emit('refresh')" :disabled="!dataset">{{ t('buttons.refresh') }}</button>
    </div>

    <div v-if="dataset" class="dataset-grid">
      <div class="stat">
        <span>{{ t('dataset.datasetId') }}</span>
        <code>{{ dataset.dataset_id }}</code>
      </div>
      <div class="stat">
        <span>{{ t('dataset.rows') }}</span>
        <strong>{{ formatNumber(dataset.n_rows, localeAsApp) }}</strong>
      </div>
      <div class="stat">
        <span>{{ t('dataset.reportDateSuggested') }}</span>
        <strong>{{ formatDate(dataset.report_date_suggested, localeAsApp) }}</strong>
      </div>
    </div>

    <div v-if="dataset" class="quality-wrap">
      <div class="quality-title">{{ t('dataset.qualityTitle') }}</div>
      <ul v-if="issues.length" class="quality-list">
        <li v-for="issue in issues" :key="issue.code" :class="['quality-item', issue.severity]">
          <span class="severity">{{ t(`common.${issue.severity}`) }}</span>
          <span>{{ issue.message }}</span>
        </li>
      </ul>
      <div v-else class="quality-ok">{{ t('datasetQuality.allGood') }}</div>
    </div>

    <div v-if="dataset" class="status-wrap">
      <h3>{{ t('dataset.topStatuses') }}</h3>
      <div class="status-chips">
        <span class="chip" v-for="[name, count] in topStatuses" :key="name">
          {{ name }}: {{ formatNumber(count, localeAsApp) }}
        </span>
      </div>
    </div>

    <div v-if="!dataset" class="empty-dataset">
      <h3>{{ t('dataset.noDataTitle') }}</h3>
      <p>{{ t('dataset.noDataHint') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AppLocale } from '../i18n/messages'
import type { DatasetQualityIssue, DatasetUploadResponse } from '../types/forecast'
import { formatDate, formatNumber } from '../utils/format'

const props = defineProps<{
  dataset: DatasetUploadResponse | null
  issues: DatasetQualityIssue[]
}>()

defineEmits<{
  (e: 'file-change', event: Event): void
  (e: 'refresh'): void
}>()

const { t, locale } = useI18n()

const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)

const topStatuses = computed(() => {
  if (!props.dataset) return []
  return Object.entries(props.dataset.status_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
})
</script>
