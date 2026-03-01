<template>
  <section class="card">
    <h2>{{ t('screen.dataset') }}</h2>
    <div class="upload-row dataset-source-row">
      <label class="upload-label">
        <span>{{ t('dataset.uploadLabel') }}</span>
        <input type="file" accept=".csv" @change="$emit('file-change', $event)" />
      </label>

      <div class="dataset-picker">
        <label>
          <span>{{ t('dataset.selectExisting') }}</span>
          <select v-model="selectedDatasetId" :disabled="datasetsLoading || datasets.length === 0">
            <option value="">{{ t('dataset.selectExistingPlaceholder') }}</option>
            <option v-for="item in datasets" :key="item.dataset_id" :value="item.dataset_id">
              {{ item.original_filename }} - {{ formatDate(item.created_at, localeAsApp) }}
            </option>
          </select>
        </label>
        <div class="row">
          <button class="btn btn-ghost" @click="$emit('refresh-datasets')" :disabled="datasetsLoading">
            {{ t('dataset.refreshList') }}
          </button>
          <button
            class="btn btn-secondary"
            :disabled="!selectedDatasetId || datasetsLoading"
            @click="onUseSelectedDataset"
          >
            {{ t('dataset.useSelected') }}
          </button>
          <button class="btn btn-secondary" @click="$emit('refresh')" :disabled="!dataset">
            {{ t('buttons.refresh') }}
          </button>
        </div>
      </div>
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
          <span>
            {{ issue.message }}
            <template v-if="issue.row_count"> ({{ formatNumber(issue.row_count, localeAsApp) }})</template>
          </span>
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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AppLocale } from '../i18n/messages'
import type { DatasetInfo, DatasetQualityIssue, DatasetUploadResponse } from '../types/forecast'
import { formatDate, formatNumber } from '../utils/format'

const props = defineProps<{
  dataset: DatasetUploadResponse | null
  datasets: DatasetInfo[]
  datasetsLoading: boolean
  issues: DatasetQualityIssue[]
}>()

const emit = defineEmits<{
  (e: 'file-change', event: Event): void
  (e: 'refresh'): void
  (e: 'refresh-datasets'): void
  (e: 'select-dataset', datasetId: string): void
}>()

const { t, locale } = useI18n()
const selectedDatasetId = ref('')

const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)

watch(
  () => props.dataset?.dataset_id,
  value => {
    selectedDatasetId.value = value ?? ''
  },
  { immediate: true },
)

const topStatuses = computed(() => {
  if (!props.dataset) return []
  return Object.entries(props.dataset.status_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
})

function onUseSelectedDataset() {
  if (!selectedDatasetId.value) return
  emit('select-dataset', selectedDatasetId.value)
}
</script>
